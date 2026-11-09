"""Endpoints to start, inspect and safely resume candidate scoring workflows."""

import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsHRStaff
from candidates.models import Candidate, CandidateStatus, ResumeProcessingStatus
from candidates.views import candidates_visible_to
from .auto import count_awaiting_scoring
from .models import WorkflowRun, WorkflowRunStatus, WorkflowTrigger
from scoring.services.agent import evaluate_candidate_resume
from .serializers import WorkflowRunSerializer
from .services import retry_workflow_resume, start_scoring_workflow

logger = logging.getLogger(__name__)


class CandidateScoringWorkflowStartView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, candidate_id):
        candidate = get_object_or_404(
            Candidate.objects.select_related("requisition"), public_id=candidate_id
        )
        if candidate.requisition.status != "OPEN":
            raise exceptions.ValidationError("Scoring workflows can only start for open requisitions.")
        if candidate.current_status not in {
            CandidateStatus.RESUME_RECEIVED,
            CandidateStatus.NEEDS_MANUAL_REVIEW,
            CandidateStatus.SCORED_HR_REVIEW,
        }:
            raise exceptions.ValidationError("This candidate is not at a status that permits resume scoring.")
        active = candidate.workflow_runs.filter(
            status__in=(
                WorkflowRunStatus.PENDING,
                WorkflowRunStatus.RUNNING,
                WorkflowRunStatus.WAITING_HR_REVIEW,
            )
        ).first()
        if active and active.status == WorkflowRunStatus.WAITING_HR_REVIEW:
            return self._rescore_waiting_run(request, candidate, active)
        if active:
            raise exceptions.ValidationError({
                "workflow": f"A workflow is already active: {active.public_id} ({active.status})."
            })
        resume = candidate.resume_documents.filter(
            processing_status=ResumeProcessingStatus.COMPLETED
        ).order_by("-processed_at", "-created_at").first()
        if not resume:
            raise exceptions.ValidationError({
                "resume": "The candidate does not have a successfully processed resume."
            })
        try:
            with transaction.atomic():
                run = WorkflowRun.objects.create(
                    candidate=candidate,
                    resume_document=resume,
                    status=WorkflowRunStatus.PENDING,
                    created_by=request.user,
                    trigger=WorkflowTrigger.MANUAL,
                )
        except IntegrityError as exc:
            # The scheduled scoring task started a run between the check above and this insert.
            raise exceptions.ValidationError({
                "workflow": "A scoring workflow was just started for this candidate. Refresh in a moment."
            }) from exc
        run = start_scoring_workflow(run)
        response_status = (
            status.HTTP_202_ACCEPTED
            if run.status == WorkflowRunStatus.WAITING_HR_REVIEW
            else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(WorkflowRunSerializer(run).data, status=response_status)


    def _rescore_waiting_run(self, request, candidate, run):
        """Re-score while the run waits for HR: add a new immutable evaluation version, leave the run paused.

        The run (status, checkpoint, gate) is untouched; only its evaluation pointer follows the new latest
        evaluation, because a shortlist decision must reference the latest one and then resumes this same run.
        """
        try:
            evaluation = evaluate_candidate_resume(candidate.pk, str(run.resume_document.public_id), actor=request.user)
        except Exception as exc:
            logger.error("Re-scoring failed. workflow_run=%s exception_type=%s", run.public_id, type(exc).__name__)
            raise exceptions.APIException("The re-score failed. The previous evaluation and workflow are unchanged; try again.")
        run.evaluation = evaluation
        run.state_summary = {
            **(run.state_summary or {}),
            "evaluation_public_id": str(evaluation.public_id),
            "overall_score": evaluation.overall_score,
            "confidence_level": str(evaluation.confidence_level),
            "recommendation": str(evaluation.recommendation_for_human_review),
        }
        run.save(update_fields=("evaluation", "state_summary", "updated_at"))
        return Response(WorkflowRunSerializer(run).data, status=status.HTTP_202_ACCEPTED)


class AutoScoringStatusView(APIView):
    """Automatic scoring configuration plus counts scoped to the candidates the user may see."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        visible = candidates_visible_to(request.user)
        last_run = (
            WorkflowRun.objects.filter(trigger=WorkflowTrigger.AUTOMATIC, candidate__in=visible)
            .order_by("-created_at").values_list("created_at", flat=True).first()
        )
        return Response({
            "enabled": settings.AUTO_SCORING_ENABLED,
            "interval_seconds": settings.AUTO_SCORING_INTERVAL_SECONDS,
            "batch_limit": settings.AUTO_SCORING_BATCH_LIMIT,
            "awaiting_scoring": count_awaiting_scoring(visible),
            "last_automatic_run_at": last_run,
        })


class WorkflowRunDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, public_id):
        run = get_object_or_404(
            WorkflowRun.objects.select_related("candidate", "candidate__requisition", "resume_document", "evaluation"),
            public_id=public_id,
        )
        user = request.user
        allowed = (
            user.is_superuser
            or getattr(user, "role", None) in ("ADMIN", "RECRUITER")
            or (
                getattr(user, "role", None) == "HIRING_MANAGER"
                and run.candidate.requisition.hiring_manager_id == user.pk
            )
        )
        if not allowed:
            raise exceptions.PermissionDenied("You cannot access this workflow.")
        return Response(WorkflowRunSerializer(run).data)


class WorkflowRunResumeView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, public_id):
        run = get_object_or_404(
            WorkflowRun.objects.select_related("candidate", "resume_document", "evaluation"),
            public_id=public_id,
        )
        try:
            run = retry_workflow_resume(run)
        except ValueError as exc:
            raise exceptions.ValidationError({"workflow": str(exc)}) from exc
        except Exception as exc:
            raise exceptions.APIException(
                "The workflow could not be resumed. The saved recruiter decision is preserved; retry later."
            ) from exc
        return Response(WorkflowRunSerializer(run).data)
