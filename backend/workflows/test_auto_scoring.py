"""Automatic (Celery-scheduled) resume scoring. Azure is never called: the LLM provider is mocked."""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateEvent, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from llm.exceptions import LLMProviderError
from requisitions.models import Requisition, RequisitionStatus
from scoring.models import ResumeEvaluation
from scoring.tests import scoring_result
from .auto import count_awaiting_scoring, run_auto_scoring_cycle
from .models import WorkflowRun, WorkflowRunStatus, WorkflowTrigger
from .tasks import AUTO_SCORE_TASK_NAME, auto_score_new_resumes

RESUME_TEXT = (
    "PLC and SCADA. Five years of controls engineering experience. "
    "Completed multiple industrial automation projects. using Allen-Bradley controls."
)


class AutoScoringTests(TestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(temp_dir.cleanup)
        checkpoint = override_settings(
            LANGGRAPH_CHECKPOINT_DB_PATH=Path(temp_dir.name) / "checkpoints.sqlite3",
            AUTO_SCORING_ENABLED=True,
            AUTO_SCORING_BATCH_LIMIT=10,
        )
        checkpoint.enable()
        self.addCleanup(checkpoint.disable)

        self.provider = Mock()
        self.provider.deployment_name = "test-deployment"
        self.provider.generate_structured.return_value = scoring_result()
        patcher = patch("scoring.services.agent.get_llm_provider", return_value=self.provider)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.recruiter = User.objects.create_user(
            username="auto-recruiter", email="auto-recruiter@example.test",
            password="Strong-Test-Password-123!", role=UserRole.ADMIN,
        )
        self.requisition = self._requisition(RequisitionStatus.OPEN)
        self.candidate = self._candidate(self.requisition)

    def _requisition(self, status, hiring_manager=None):
        return Requisition.objects.create(
            title="Controls Engineer", department="Engineering",
            description="PLC and SCADA engineering.", responsibilities="Design and test control systems.",
            required_skills=["PLC", "SCADA"], minimum_experience_years="3.0",
            status=status, created_by=self.recruiter, hiring_manager=hiring_manager,
        )

    def _candidate(self, requisition, resume_status=ResumeProcessingStatus.COMPLETED, **fields):
        candidate = Candidate.objects.create(
            requisition=requisition, full_name="Synthetic Candidate",
            email=f"synthetic{Candidate.objects.count()}@example.test", created_by=self.recruiter, **fields,
        )
        ResumeDocument.objects.create(
            candidate=candidate, file="resumes/test.docx", original_filename="test.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=100, sha256="a" * 64, processing_status=resume_status,
            extracted_text=RESUME_TEXT if resume_status == ResumeProcessingStatus.COMPLETED else "",
            created_by=self.recruiter,
        )
        return candidate

    def test_new_resume_is_scored_automatically_and_paused_at_the_human_gate(self):
        summary = run_auto_scoring_cycle()

        self.assertEqual((summary["started"], summary["scored"], summary["failed"]), (1, 1, 0))
        run = WorkflowRun.objects.get(candidate=self.candidate)
        self.assertEqual(run.trigger, WorkflowTrigger.AUTOMATIC)
        self.assertIsNone(run.created_by)
        self.assertEqual(run.status, WorkflowRunStatus.WAITING_HR_REVIEW)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCORED_HR_REVIEW)
        evaluation = ResumeEvaluation.objects.get(candidate=self.candidate)
        self.assertIsNotNone(evaluation.overall_score)
        started = CandidateEvent.objects.get(candidate=self.candidate, event_type=CandidateEvent.EventType.WORKFLOW_STARTED)
        self.assertIsNone(started.actor)
        self.assertEqual(started.details["trigger"], WorkflowTrigger.AUTOMATIC)

    def test_each_resume_is_scored_only_once(self):
        run_auto_scoring_cycle()
        summary = run_auto_scoring_cycle()
        self.assertEqual(summary["started"], 0)
        self.assertEqual(self.provider.generate_structured.call_count, 1)
        self.assertEqual(ResumeEvaluation.objects.filter(candidate=self.candidate).count(), 1)

    def test_failed_automatic_run_is_left_for_hr_and_not_retried_every_cycle(self):
        self.provider.generate_structured.side_effect = LLMProviderError("provider down")
        first = run_auto_scoring_cycle()
        second = run_auto_scoring_cycle()

        self.assertEqual((first["started"], first["failed"]), (1, 1))
        self.assertEqual(second["started"], 0)
        self.assertEqual(self.provider.generate_structured.call_count, 1)
        run = WorkflowRun.objects.get(candidate=self.candidate)
        self.assertEqual(run.status, WorkflowRunStatus.FAILED)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.RESUME_RECEIVED)

        # An operator can re-run failed resumes after fixing the provider (auto_score_resumes --retry-failed).
        self.provider.generate_structured.side_effect = None
        retried = run_auto_scoring_cycle(retry_failed=True)
        self.assertEqual((retried["started"], retried["scored"]), (1, 1))
        self.assertEqual(WorkflowRun.objects.filter(candidate=self.candidate).count(), 2)  # failed run kept for audit

    def test_hr_can_retry_a_failed_automatic_run_manually(self):
        self.provider.generate_structured.side_effect = LLMProviderError("provider down")
        run_auto_scoring_cycle()
        self.provider.generate_structured.side_effect = None
        client = APIClient()
        client.force_authenticate(self.recruiter)
        response = client.post(f"/api/v1/workflows/candidates/{self.candidate.public_id}/start-scoring/")
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["trigger"], WorkflowTrigger.MANUAL)

    def test_ineligible_candidates_are_skipped(self):
        self.candidate.current_status = CandidateStatus.CLOSED
        self.candidate.save(update_fields=("current_status",))
        self._candidate(self._requisition(RequisitionStatus.ON_HOLD))
        self._candidate(self.requisition, resume_status=ResumeProcessingStatus.NEEDS_MANUAL_REVIEW)
        self._candidate(self.requisition, resume_status=ResumeProcessingStatus.FAILED)

        summary = run_auto_scoring_cycle()
        self.assertEqual(summary["started"], 0)
        self.provider.generate_structured.assert_not_called()

    def test_candidate_with_an_active_run_is_skipped(self):
        WorkflowRun.objects.create(
            candidate=self.candidate, resume_document=self.candidate.resume_documents.get(),
            status=WorkflowRunStatus.RUNNING, created_by=self.recruiter,
        )
        self.assertEqual(run_auto_scoring_cycle()["started"], 0)

    def test_database_allows_only_one_active_run_per_candidate(self):
        resume = self.candidate.resume_documents.get()
        WorkflowRun.objects.create(candidate=self.candidate, resume_document=resume, status=WorkflowRunStatus.PENDING)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WorkflowRun.objects.create(candidate=self.candidate, resume_document=resume, status=WorkflowRunStatus.RUNNING)
        # Finished runs do not count.
        WorkflowRun.objects.create(candidate=self.candidate, resume_document=resume, status=WorkflowRunStatus.FAILED)

    def test_batch_limit_is_respected(self):
        self._candidate(self.requisition)
        self._candidate(self.requisition)
        self.assertEqual(run_auto_scoring_cycle(limit=2)["started"], 2)
        self.assertEqual(run_auto_scoring_cycle(limit=2)["started"], 1)

    def test_stale_run_is_released_for_hr_retry(self):
        run = WorkflowRun.objects.create(
            candidate=self.candidate, resume_document=self.candidate.resume_documents.get(),
            status=WorkflowRunStatus.RUNNING, trigger=WorkflowTrigger.AUTOMATIC,
        )
        WorkflowRun.objects.filter(pk=run.pk).update(updated_at=timezone.now() - timedelta(minutes=30))

        summary = run_auto_scoring_cycle()
        run.refresh_from_db()
        self.assertEqual(summary["released_stale"], 1)
        self.assertEqual((run.status, run.error_code), (WorkflowRunStatus.FAILED, "WORKFLOW_STALE"))
        self.assertTrue(CandidateEvent.objects.filter(
            candidate=self.candidate, event_type=CandidateEvent.EventType.WORKFLOW_FAILED,
            details__error_code="WORKFLOW_STALE",
        ).exists())
        self.assertEqual(summary["started"], 0)  # that resume already had its automatic attempt

    def test_pending_resumes_are_extracted_first(self):
        pending = self._candidate(self.requisition, resume_status=ResumeProcessingStatus.PENDING)
        with patch("workflows.auto.process_resume_document") as extract:
            summary = run_auto_scoring_cycle()
        self.assertEqual(summary["extracted"], 1)
        extract.assert_called_once()
        self.assertEqual(extract.call_args.args[0].candidate_id, pending.pk)

    def test_celery_task_runs_a_cycle_without_a_broker(self):
        result = auto_score_new_resumes.apply().get()
        self.assertEqual(result["scored"], 1)

    @override_settings(AUTO_SCORING_ENABLED=False)
    def test_disabled_task_does_nothing(self):
        self.assertEqual(auto_score_new_resumes.apply().get(), {"enabled": False})
        self.provider.generate_structured.assert_not_called()
        self.assertFalse(WorkflowRun.objects.exists())

    def test_beat_schedule_runs_the_task_every_interval(self):
        from config.celery import app

        entry = app.conf.beat_schedule["auto-score-new-resumes"]
        self.assertEqual(entry["task"], AUTO_SCORE_TASK_NAME)
        self.assertEqual(entry["schedule"], float(settings.AUTO_SCORING_INTERVAL_SECONDS))
        app.loader.import_default_modules()
        self.assertIn(AUTO_SCORE_TASK_NAME, app.tasks)

    def test_status_endpoint_is_scoped_to_visible_candidates(self):
        client = APIClient()
        self.assertEqual(client.get("/api/v1/workflows/auto-scoring/").status_code, 401)

        client.force_authenticate(self.recruiter)
        data = client.get("/api/v1/workflows/auto-scoring/").json()
        self.assertTrue(data["enabled"])
        self.assertEqual(data["interval_seconds"], settings.AUTO_SCORING_INTERVAL_SECONDS)
        self.assertEqual(data["awaiting_scoring"], 1)
        self.assertIsNone(data["last_automatic_run_at"])

        manager = User.objects.create_user(
            username="auto-manager", email="auto-manager@example.test",
            password="Strong-Test-Password-123!", role=UserRole.RECRUITER,
        )
        client.force_authenticate(manager)
        self.assertEqual(client.get("/api/v1/workflows/auto-scoring/").json()["awaiting_scoring"], 0)

        run_auto_scoring_cycle()
        client.force_authenticate(self.recruiter)
        data = client.get("/api/v1/workflows/auto-scoring/").json()
        self.assertEqual(data["awaiting_scoring"], 0)
        self.assertIsNotNone(data["last_automatic_run_at"])
        self.assertEqual(count_awaiting_scoring(), 0)
