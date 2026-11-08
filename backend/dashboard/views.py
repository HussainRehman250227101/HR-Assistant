"""Read-only dashboard (SRS §5 scope, FR-12, FR-13, AC-09): lifecycle counts, actionable work, pipeline, audit log.

Every query is scoped through `candidates_visible_to`, so an interviewer-only recruiter sees just their assigned candidates.
"""

from datetime import timedelta

from django.db.models import Count, OuterRef, Q, Subquery
from django.utils import timezone
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from candidates.models import CandidateEvent, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from candidates.serializers import CandidateEventSerializer
from candidates.views import candidates_visible_to
from communications.models import ApprovalStatus, CommunicationLog, SendStatus
from accounts.permissions import has_full_access
from requisitions.models import Requisition, RequisitionStatus
from scheduling.models import Interview, InterviewStatus
from scoring.models import ResumeEvaluation
from screening.models import Screening, ScreeningStatus
from workflows.models import WorkflowRun, WorkflowRunStatus


def _scoped(request):
    candidates = candidates_visible_to(request.user)
    requisition = request.query_params.get("requisition")
    if requisition:
        candidates = candidates.filter(requisition__reference_code=requisition)
    return candidates


class DashboardSummaryView(APIView):
    def get(self, request):
        candidates = _scoped(request)
        now = timezone.now()
        status_counts = dict(candidates.order_by().values_list("current_status").annotate(n=Count("id")))
        by_status = [{"status": value, "label": label, "count": status_counts.get(value, 0)}
                     for value, label in CandidateStatus.choices]

        screenings = Screening.objects.filter(candidate__in=candidates)
        interviews = Interview.objects.filter(candidate__in=candidates)
        messages = CommunicationLog.objects.filter(candidate__in=candidates)
        resumes = ResumeDocument.objects.filter(candidate__in=candidates)
        attention = [
            ("SHORTLIST_REVIEW", "Candidates awaiting shortlist decision", "/shortlist", "warning",
             candidates.filter(current_status=CandidateStatus.SCORED_HR_REVIEW).count()),
            ("MANUAL_REVIEW", "Candidates needing manual review", "/candidates?status=NEEDS_MANUAL_REVIEW", "warning",
             candidates.filter(current_status=CandidateStatus.NEEDS_MANUAL_REVIEW).count()),
            ("RESUME_FAILED", "Resume extraction failures (retryable)", "/candidates?status=RESUME_RECEIVED", "critical",
             resumes.filter(processing_status=ResumeProcessingStatus.FAILED).count()),
            ("RESUME_PENDING", "Resumes waiting for text extraction", "/candidates?status=RESUME_RECEIVED", "info",
             resumes.filter(processing_status=ResumeProcessingStatus.PENDING).count()),
            ("WORKFLOW_FAILED", "Scoring workflows failed", "/candidates", "critical",
             WorkflowRun.objects.filter(candidate__in=candidates, status=WorkflowRunStatus.FAILED).count()),
            ("APPROVED_NOT_SCREENED", "Approved for screening, not yet contacted", "/candidates?status=APPROVED_FOR_SCREENING", "info",
             candidates.filter(current_status=CandidateStatus.APPROVED_FOR_SCREENING).count()),
            ("CALLS_PENDING", "AI screenings to run (browser session or call)", "/screening", "info",
             screenings.filter(status=ScreeningStatus.PENDING_CALL).count()),
            ("SCREENING_ANALYSIS_FAILED", "Screening analysis failures", "/screening", "critical",
             screenings.filter(status=ScreeningStatus.ANALYSIS_FAILED).count()),
            ("SCREENING_REVIEW", "Screening results awaiting HR decision", "/screening", "warning",
             screenings.filter(status=ScreeningStatus.AWAITING_HR_REVIEW).count()),
            ("HUMAN_SCREENING", "Human-led screenings to record", "/screening", "info",
             screenings.filter(status=ScreeningStatus.AWAITING_MANUAL_RESULT).count()),
            ("INTERVIEW_TO_PLAN", "Approved for interview, not yet planned", "/candidates?status=APPROVED_FOR_INTERVIEW", "info",
             candidates.filter(current_status=CandidateStatus.APPROVED_FOR_INTERVIEW).count()),
            ("NO_SHARED_AVAILABILITY", "Interviews needing manual coordination", "/interviews", "warning",
             interviews.filter(status=InterviewStatus.NEEDS_HR_COORDINATION).count()),
            ("SLOT_TO_CONFIRM", "Proposed interview slots to confirm", "/interviews", "info",
             interviews.filter(status=InterviewStatus.PROPOSED).count()),
            ("INVITATION_TO_SEND", "Confirmed slots awaiting invitation approval", "/interviews", "warning",
             interviews.filter(status=InterviewStatus.SLOT_CONFIRMED).count()),
            ("EMAIL_FAILED", "Emails that failed to send", "/interviews", "critical",
             messages.filter(send_status=SendStatus.FAILED).count()),
            ("CANCELLATION_DRAFTS", "Cancellation notices awaiting approval", "/interviews", "warning",
             messages.filter(kind="INTERVIEW_CANCELLATION", approval_status=ApprovalStatus.DRAFT).count()),
        ]
        upcoming = interviews.filter(
            status=InterviewStatus.SCHEDULED, confirmed_start__gte=now, confirmed_start__lte=now + timedelta(days=14),
        ).select_related("candidate", "interviewer", "requisition").order_by("confirmed_start")[:10]
        requisitions = Requisition.objects.filter(status=RequisitionStatus.OPEN)
        if not has_full_access(request.user):
            requisitions = requisitions.filter(interviews__interviewer=request.user).distinct()
        return Response({
            "generated_at": now,
            "total_candidates": sum(status_counts.values()),
            "active_candidates": sum(n for s, n in status_counts.items() if s != CandidateStatus.CLOSED),
            "open_requisitions": requisitions.count(),
            "by_status": by_status,
            "attention": [
                {"key": k, "label": label, "link": link, "severity": sev, "count": n}
                for k, label, link, sev, n in attention if n
            ],
            "upcoming_interviews": [{
                "interview_id": str(i.public_id), "candidate_id": str(i.candidate.public_id),
                "candidate_name": i.candidate.full_name, "requisition_title": i.requisition.title,
                "interviewer_name": i.interviewer.get_full_name() or i.interviewer.username,
                "start": i.confirmed_start, "timezone": i.timezone, "mode": i.mode,
            } for i in upcoming],
        })


class PipelinePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


class PipelineView(APIView):
    """One row per candidate: status, latest score, latest screening outcome, interview slot."""

    def get(self, request):
        candidates = _scoped(request).select_related("requisition")
        status_filter = request.query_params.get("status")
        if status_filter:
            if status_filter not in CandidateStatus.values:
                raise exceptions.ValidationError({"status": "Invalid candidate status."})
            candidates = candidates.filter(current_status=status_filter)
        search = request.query_params.get("search")
        if search:
            candidates = candidates.filter(Q(full_name__icontains=search) | Q(email__icontains=search))
        latest_eval = ResumeEvaluation.objects.filter(candidate=OuterRef("pk")).order_by("-created_at", "-version")
        latest_screening = Screening.objects.filter(candidate=OuterRef("pk")).order_by("-created_at")
        latest_interview = Interview.objects.filter(candidate=OuterRef("pk")).order_by("-created_at")
        candidates = candidates.annotate(
            score=Subquery(latest_eval.values("overall_score")[:1]),
            confidence=Subquery(latest_eval.values("confidence_level")[:1]),
            screening_status=Subquery(latest_screening.values("status")[:1]),
            screening_call_status=Subquery(latest_screening.values("call_status")[:1]),
            interview_status=Subquery(latest_interview.values("status")[:1]),
            interview_start=Subquery(latest_interview.values("confirmed_start")[:1]),
            interview_timezone=Subquery(latest_interview.values("timezone")[:1]),
        ).order_by("-updated_at")
        paginator = PipelinePagination()
        page = paginator.paginate_queryset(candidates, request, view=self)
        return paginator.get_paginated_response([{
            "public_id": str(c.public_id), "name": c.full_name or "Identity details pending review",
            "requisition_title": c.requisition.title, "requisition_reference": str(c.requisition.reference_code),
            "current_status": c.current_status, "score": c.score, "confidence": c.confidence,
            "screening_status": c.screening_status, "screening_call_status": c.screening_call_status,
            "interview_status": c.interview_status, "interview_start": c.interview_start,
            "interview_timezone": c.interview_timezone, "updated_at": c.updated_at,
        } for c in page])


class ActivityPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class ActivityLogView(APIView):
    """Cross-candidate audit trail (FR-14, SRS §13): approvals, calls, calendar checks, emails, status changes."""

    def get(self, request):
        events = CandidateEvent.objects.filter(candidate__in=_scoped(request)).select_related("actor", "candidate")
        event_type = request.query_params.get("event_type")
        if event_type:
            events = events.filter(event_type=event_type)
        candidate = request.query_params.get("candidate")
        if candidate:
            events = events.filter(candidate__public_id=candidate)
        paginator = ActivityPagination()
        page = paginator.paginate_queryset(events.order_by("-created_at"), request, view=self)
        rows = []
        for event in page:
            data = CandidateEventSerializer(event).data
            data["candidate_id"] = str(event.candidate.public_id)
            data["candidate_name"] = event.candidate.full_name or "Identity pending"
            rows.append(data)
        return paginator.get_paginated_response(rows)


class EventTypesView(APIView):
    def get(self, request):
        return Response([{"value": v, "label": label} for v, label in CandidateEvent.EventType.choices])
