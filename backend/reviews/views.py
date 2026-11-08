"""Recruiter-controlled shortlist review and candidate progression."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.permissions import IsHRStaff
from candidates.models import Candidate, CandidateEvent, CandidateStatus
from candidates.services.decline import mark_declined
from candidates.tasks import queue_declined_processing
from scoring.models import ResumeEvaluation
from scoring.serializers import EvaluationListSerializer
from workflows.models import WorkflowRun, WorkflowRunStatus
from workflows.services import resume_workflow_after_review
from .models import ShortlistDecision, ShortlistReview
from .serializers import ShortlistDecisionRequestSerializer, ShortlistReviewSerializer


REVIEWABLE_STATUSES = {CandidateStatus.SCORED_HR_REVIEW, CandidateStatus.NEEDS_MANUAL_REVIEW}


class ShortlistQueueView(GenericAPIView):
    permission_classes = [IsHRStaff]

    def get(self, request):
        queryset = Candidate.objects.filter(
            current_status__in=REVIEWABLE_STATUSES
        ).select_related("requisition")
        requisition_ref = request.query_params.get("requisition")
        if requisition_ref:
            queryset = queryset.filter(requisition__reference_code=requisition_ref)
        results = []
        for candidate in queryset.order_by("-updated_at"):
            evaluation = candidate.resume_evaluations.select_related("rubric").order_by("-created_at", "-version").first()
            if evaluation:
                results.append({
                    "candidate": {
                        "public_id": str(candidate.public_id),
                        "full_name": candidate.full_name,
                        "email": candidate.email,
                        "phone": candidate.phone,
                        "current_status": candidate.current_status,
                        "identity_review_required": candidate.identity_review_required,
                        "requisition_reference": str(candidate.requisition.reference_code),
                        "requisition_title": candidate.requisition.title,
                    },
                    "evaluation": EvaluationListSerializer(evaluation).data,
                })
        return Response({"count": len(results), "results": results})


class CandidateShortlistDecisionView(GenericAPIView):
    permission_classes = [IsHRStaff]
    serializer_class = ShortlistDecisionRequestSerializer

    def post(self, request, candidate_id):
        candidate = get_object_or_404(
            Candidate.objects.select_related("requisition"), public_id=candidate_id
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        evaluation = get_object_or_404(ResumeEvaluation, public_id=data["evaluation"])

        if evaluation.candidate_id != candidate.pk:
            raise exceptions.ValidationError({"evaluation": "The selected evaluation does not belong to this candidate."})
        latest = candidate.resume_evaluations.order_by("-created_at", "-version").first()
        if latest is None or latest.pk != evaluation.pk:
            raise exceptions.ValidationError({"evaluation": "A shortlist decision must reference the candidate's latest evaluation."})
        if candidate.current_status not in REVIEWABLE_STATUSES:
            raise exceptions.ValidationError({"candidate_status": "This candidate is not awaiting recruiter shortlist review."})

        if data["decision"] == ShortlistDecision.APPROVE_FOR_SCREENING:
            # If the AI could not calculate a score, approval requires a reasoned human score override.
            if evaluation.overall_score is None and data.get("score_override") is None:
                raise exceptions.ValidationError({
                    "decision": "This evaluation has no defensible overall score. Provide a reasoned human score override or keep the candidate for manual review."
                })
            # Name and contact details are read from the resume automatically; HR only adds one if the resume had none.
            if not (candidate.email or candidate.phone):
                raise exceptions.ValidationError({"candidate_details": "No email or phone number was found in this candidate's resume. Add one with Edit details, then approve."})

        previous_status = candidate.current_status
        if data["decision"] == ShortlistDecision.APPROVE_FOR_SCREENING:
            resulting_status = CandidateStatus.APPROVED_FOR_SCREENING
        elif data["decision"] == ShortlistDecision.DECLINE:
            resulting_status = CandidateStatus.CLOSED
        else:
            resulting_status = CandidateStatus.NEEDS_MANUAL_REVIEW

        with transaction.atomic():
            review = ShortlistReview.objects.create(
                candidate=candidate,
                evaluation=evaluation,
                decision=data["decision"],
                decision_reason=data["decision_reason"],
                score_override=data.get("score_override"),
                score_override_reason=data.get("score_override_reason", ""),
                previous_candidate_status=previous_status,
                resulting_candidate_status=resulting_status,
                decided_by=request.user,
            )
            identity_was_pending = candidate.identity_review_required
            approving = data["decision"] == ShortlistDecision.APPROVE_FOR_SCREENING
            candidate.current_status = resulting_status
            if approving:
                # The recruiter's approval confirms the details the system read from the resume.
                candidate.identity_review_required = False
            if resulting_status == CandidateStatus.CLOSED:
                candidate.closed_reason = data["decision_reason"]
                candidate.save(update_fields=("current_status", "closed_reason", "identity_review_required", "updated_at"))
            else:
                candidate.save(update_fields=("current_status", "identity_review_required", "updated_at"))
            if identity_was_pending and approving:
                CandidateEvent.objects.create(
                    candidate=candidate, actor=request.user,
                    event_type=CandidateEvent.EventType.CANDIDATE_IDENTITY_REVIEWED,
                    details={
                        "review_reason": data.get("identity_review_reason", "") or "Confirmed by approving the candidate",
                        "fields_from_resume": list(candidate.auto_filled_fields or []),
                    },
                )
            CandidateEvent.objects.create(
                candidate=candidate, actor=request.user,
                event_type=CandidateEvent.EventType.SHORTLIST_DECISION_RECORDED,
                details={
                    "shortlist_review_id": str(review.public_id),
                    "evaluation_id": str(evaluation.public_id),
                    "decision": review.decision,
                    "from": previous_status,
                    "to": resulting_status,
                    "score_override": review.score_override,
                },
            )
            if resulting_status == CandidateStatus.CLOSED:
                mark_declined(candidate, request.user, "SHORTLIST_REVIEW")  # rejection email + data deletion follow

        run = WorkflowRun.objects.filter(
            evaluation=evaluation,
            status=WorkflowRunStatus.WAITING_HR_REVIEW,
        ).order_by("-created_at").first()
        if run:
            try:
                resume_workflow_after_review(run, review)
            except Exception:
                # The decision is durable; POST /api/v1/workflows/<run_uuid>/resume/ retries safely.
                run.refresh_from_db()

        if resulting_status == CandidateStatus.CLOSED:
            # After the workflow resume above, so the deletion never races the scoring workflow.
            queue_declined_processing(candidate.pk)

        return Response({
            "review": ShortlistReviewSerializer(review).data,
            "candidate_status": resulting_status,
            "workflow_run": str(run.public_id) if run else None,
            "workflow_status": run.status if run else None,
        }, status=status.HTTP_201_CREATED)


class CandidateShortlistHistoryView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, candidate_id):
        candidate = get_object_or_404(Candidate, public_id=candidate_id)
        user = request.user
        allowed = (
            user.is_superuser
            or getattr(user, "role", None) in ("ADMIN", "RECRUITER")
            or (
                getattr(user, "role", None) == "HIRING_MANAGER"
                and candidate.requisition.hiring_manager_id == user.pk
            )
        )
        if not allowed:
            raise exceptions.PermissionDenied("You cannot access this review history.")
        reviews = candidate.shortlist_reviews.select_related("evaluation", "decided_by").all()
        return Response(ShortlistReviewSerializer(reviews, many=True).data)
