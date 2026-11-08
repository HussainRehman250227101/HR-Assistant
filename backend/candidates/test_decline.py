"""Declined candidates: friendly rejection email, then automatic deletion of their data (name kept)."""

from unittest.mock import patch

from django.core import mail
from django.test import TestCase, override_settings

from accounts.models import User, UserRole
from audit.models import AuditEvent
from communications.models import CommunicationLog, MessageKind, SendStatus
from requisitions.models import Requisition, RequisitionStatus
from scoring.models import ConfidenceLevel, EvaluationRecommendation, ResumeEvaluation, ScoringRubric
from screening.models import Screening, ScreeningDecision, ScreeningStatus
from screening.services.review import review_screening
from workflows.models import WorkflowRun, WorkflowRunStatus
from .models import Candidate, CandidateEvent, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from .services.decline import DeclineOutcome, declined_awaiting_processing, mark_declined, process_declined_candidate

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
EVENT = CandidateEvent.EventType


class DeclineFixture:
    def make(self):
        self.hr = User.objects.create_user("hr", "hr@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department="Eng", description="APIs", status=RequisitionStatus.OPEN,
            created_by=self.hr,
        )
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Ayesha Khan", email="ayesha@example.test", phone="03001234567",
            location="Lahore", linkedin_url="https://linkedin.example/ayesha", created_by=self.hr,
            current_status=CandidateStatus.CLOSED, closed_reason="Not enough Django experience",
        )
        self.document = ResumeDocument.objects.create(
            candidate=self.candidate, file="resumes/ayesha.docx", original_filename="Ayesha Khan CV.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document", file_size=50,
            sha256="a" * 64, processing_status=ResumeProcessingStatus.COMPLETED,
            extracted_text="Ayesha Khan, Lahore. Python developer.", created_by=self.hr,
        )
        rubric = ScoringRubric.objects.create(requisition=self.requisition)
        self.evaluation = ResumeEvaluation.objects.create(
            candidate=self.candidate, requisition=self.requisition, resume_document=self.document, rubric=rubric,
            version=1, overall_score=40, assessed_weight=100, criterion_scores={}, evidence={"Python": ["Python developer"]},
            missing_or_unclear_items=["Django"], parsing_warnings=[], confidence_level=ConfidenceLevel.HIGH,
            recommendation_for_human_review=EvaluationRecommendation.REVIEW_RECOMMENDED,
            overall_assessment="Limited Django evidence.", model_version="m", input_sha256="a" * 64, created_by=self.hr,
        )
        self.screening = Screening.objects.create(
            candidate=self.candidate, requisition=self.requisition, status=ScreeningStatus.REVIEWED, questions=["Q"],
            script_version="v", created_by=self.hr, transcript=[{"role": "candidate", "message": "I live in Lahore"}],
            concise_summary="Summary with personal details", candidate_stated_availability="Monday 10 to 2",
        )
        mark_declined(self.candidate, self.hr, "SHORTLIST_REVIEW")

    def rejection_logs(self):
        return CommunicationLog.objects.filter(candidate=self.candidate, kind=MessageKind.REJECTION)


@override_settings(EMAIL_BACKEND=LOCMEM, SCREENING_ORGANIZATION_NAME="Netsol", REJECTION_AUTO_ENABLED=True)
class DeclineProcessingTests(DeclineFixture, TestCase):
    def setUp(self):
        self.make()

    def test_friendly_email_is_sent_then_data_is_erased_and_only_the_name_is_kept(self):
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.ERASED)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["ayesha@example.test"])
        self.assertEqual(message.subject, "Update on your application for Backend Engineer at Netsol")
        body = message.body
        self.assertTrue(body.startswith("Hi Ayesha,"))
        self.assertIn("Thank you so much", body)
        self.assertIn("deleted your resume, your contact details, your screening answers and our evaluation notes", body)
        self.assertIn("Warm regards", body)
        # The email does not mention keeping the name, and does not disclose HR's reason or any score.
        lowered = body.lower()
        for word in ("retain", "keep your", "kept", "name", "not enough django", "40"):
            self.assertNotIn(word, lowered)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.full_name, "Ayesha Khan")  # name only, so HR knows who was declined
        self.assertEqual(self.candidate.current_status, CandidateStatus.CLOSED)
        self.assertIsNotNone(self.candidate.personal_data_erased_at)
        self.assertIsNone(self.candidate.email)
        self.assertEqual((self.candidate.phone, self.candidate.location, self.candidate.linkedin_url), ("", "", ""))
        self.document.refresh_from_db()
        self.assertEqual((self.document.extracted_text, self.document.original_filename, bool(self.document.file)), ("", "erased", False))
        self.evaluation.refresh_from_db()
        self.assertEqual((self.evaluation.evidence, self.evaluation.overall_assessment, self.evaluation.missing_or_unclear_items), ({}, "", []))
        self.screening.refresh_from_db()
        self.assertEqual((self.screening.transcript, self.screening.candidate_stated_availability), ([], ""))
        log = self.rejection_logs().get()
        self.assertEqual((log.send_status, log.auto_sent, log.body), (SendStatus.SENT, True, "[erased]"))
        self.assertEqual(log.recipient, "redacted@example.invalid")
        types = set(CandidateEvent.objects.filter(candidate=self.candidate).values_list("event_type", flat=True))
        self.assertTrue({EVENT.REJECTION_EMAIL_SENT, EVENT.PERSONAL_DATA_ERASED} <= types)
        erased = CandidateEvent.objects.get(candidate=self.candidate, event_type=EVENT.PERSONAL_DATA_ERASED)
        self.assertTrue(erased.details["name_kept"])
        self.assertTrue(AuditEvent.objects.filter(action="CANDIDATE_PERSONAL_DATA_ERASED", details__name_kept=True).exists())

    def test_running_again_never_sends_a_second_email(self):
        process_declined_candidate(self.candidate.pk)
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.SKIPPED)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.rejection_logs().count(), 1)
        self.assertFalse(declined_awaiting_processing().filter(pk=self.candidate.pk).exists())

    def test_send_failure_keeps_the_data_and_is_retried_until_it_works(self):
        with patch("communications.services.EmailMessage.send", side_effect=OSError("smtp down")):
            self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.EMAIL_FAILED)
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.personal_data_erased_at)  # nothing deleted before the email went out
        self.assertEqual(self.candidate.email, "ayesha@example.test")
        self.document.refresh_from_db()
        self.assertEqual(self.document.extracted_text, "Ayesha Khan, Lahore. Python developer.")
        log = self.rejection_logs().get()
        self.assertEqual((log.send_status, log.send_attempts), (SendStatus.FAILED, 1))
        self.assertEqual(len(mail.outbox), 0)
        self.assertTrue(declined_awaiting_processing().filter(pk=self.candidate.pk).exists())
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.ERASED)  # retry succeeds
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(self.rejection_logs().count(), 1)
        self.assertEqual(self.rejection_logs().get().send_status, SendStatus.SENT)

    def test_sweep_stops_after_the_maximum_number_of_failed_attempts(self):
        with patch("communications.services.EmailMessage.send", side_effect=OSError("smtp down")):
            process_declined_candidate(self.candidate.pk)
        self.rejection_logs().update(send_attempts=5)
        self.assertFalse(declined_awaiting_processing().filter(pk=self.candidate.pk).exists())

    def test_candidate_without_an_email_address_is_erased_without_an_email(self):
        Candidate.objects.filter(pk=self.candidate.pk).update(email=None)
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.ERASED)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(self.rejection_logs().exists())
        self.assertTrue(CandidateEvent.objects.filter(candidate=self.candidate, event_type=EVENT.REJECTION_EMAIL_SKIPPED).exists())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.full_name, "Ayesha Khan")
        self.assertIsNotNone(self.candidate.personal_data_erased_at)

    def test_candidates_closed_any_other_way_are_never_emailed_or_erased(self):
        CandidateEvent.objects.filter(event_type=EVENT.REJECTION_PENDING).delete()  # manual closure / pre-feature decline
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.SKIPPED)
        self.assertFalse(declined_awaiting_processing().filter(pk=self.candidate.pk).exists())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.email, "ayesha@example.test")
        self.assertIsNone(self.candidate.personal_data_erased_at)
        self.assertEqual(len(mail.outbox), 0)

    def test_open_candidates_are_never_processed(self):
        Candidate.objects.filter(pk=self.candidate.pk).update(current_status=CandidateStatus.SCORED_HR_REVIEW)
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.SKIPPED)
        self.assertEqual(len(mail.outbox), 0)

    def test_a_running_scoring_workflow_delays_the_deletion(self):
        WorkflowRun.objects.create(candidate=self.candidate, resume_document=self.document, status=WorkflowRunStatus.RUNNING)
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.WAITING)
        self.assertEqual(len(mail.outbox), 0)
        self.candidate.refresh_from_db()
        self.assertIsNone(self.candidate.personal_data_erased_at)

    def test_switched_off_does_nothing(self):
        with override_settings(REJECTION_AUTO_ENABLED=False):
            self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.SKIPPED)
            Candidate.objects.filter(pk=self.candidate.pk).update(current_status=CandidateStatus.CLOSED)
            CandidateEvent.objects.filter(event_type=EVENT.REJECTION_PENDING).delete()
            mark_declined(self.candidate, self.hr, "SHORTLIST_REVIEW")
            self.assertFalse(CandidateEvent.objects.filter(event_type=EVENT.REJECTION_PENDING).exists())
        self.assertEqual(len(mail.outbox), 0)


@override_settings(EMAIL_BACKEND=LOCMEM, REJECTION_AUTO_ENABLED=True)
class DeclineTriggerTests(DeclineFixture, TestCase):
    def test_screening_decline_marks_the_candidate_and_queues_processing_after_commit(self):
        self.make()
        CandidateEvent.objects.filter(event_type=EVENT.REJECTION_PENDING).delete()
        Candidate.objects.filter(pk=self.candidate.pk).update(current_status=CandidateStatus.SCREENING_COMPLETED_HR_REVIEW, closed_reason="")
        Screening.objects.filter(pk=self.screening.pk).update(status=ScreeningStatus.AWAITING_HR_REVIEW)
        with patch("candidates.tasks.queue_declined_processing") as queue:
            with self.captureOnCommitCallbacks(execute=True):
                review_screening(Screening.objects.get(pk=self.screening.pk), self.hr, ScreeningDecision.DECLINE, "Not a fit")
            queue.assert_called_once_with(self.candidate.pk)
        marker = CandidateEvent.objects.get(candidate=self.candidate, event_type=EVENT.REJECTION_PENDING)
        self.assertEqual((marker.actor, marker.details["source"]), (self.hr, "SCREENING_REVIEW"))
        self.assertEqual(process_declined_candidate(self.candidate.pk), DeclineOutcome.ERASED)
        self.assertEqual(len(mail.outbox), 1)

    def test_approving_or_rescreening_does_not_mark_the_candidate(self):
        self.make()
        CandidateEvent.objects.filter(event_type=EVENT.REJECTION_PENDING).delete()
        Candidate.objects.filter(pk=self.candidate.pk).update(current_status=CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        Screening.objects.filter(pk=self.screening.pk).update(status=ScreeningStatus.AWAITING_HR_REVIEW)
        with patch("scheduling.tasks.queue_auto_scheduling"):
            with self.captureOnCommitCallbacks(execute=True):
                review_screening(Screening.objects.get(pk=self.screening.pk), self.hr, ScreeningDecision.APPROVE_FOR_INTERVIEW, "")
        self.assertFalse(CandidateEvent.objects.filter(event_type=EVENT.REJECTION_PENDING).exists())
