"""Scheduled automatic resume scoring, run by the Celery worker (see workflows/tasks.py).

Each cycle:
1. extracts resumes still waiting for text extraction (same service as `process_pending_resumes`);
2. releases scoring runs that stopped mid-way (e.g. the worker was killed), so HR can re-score them;
3. starts the existing LangGraph scoring workflow for every new resume: candidate in RESUME_RECEIVED,
   requisition OPEN, a successfully extracted resume that has never had a workflow run.

The workflow still pauses at the human shortlist gate. Automatic scoring never approves, declines or
contacts a candidate. Each resume is scored automatically at most once; a failed automatic run is left for
HR to retry with "Score resume", so a provider outage cannot cause repeated billed calls every cycle.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from candidates.models import (
    Candidate,
    CandidateEvent,
    CandidateStatus,
    ResumeDocument,
    ResumeProcessingStatus,
)
from candidates.services.processing import process_documents_parallel
from requisitions.models import RequisitionStatus
from .models import ACTIVE_WORKFLOW_STATUSES, WorkflowRun, WorkflowRunStatus, WorkflowTrigger
from .services import start_scoring_workflow

logger = logging.getLogger(__name__)

# A run still PENDING/RUNNING after this long has lost its worker (Azure calls time out far sooner).
STALE_RUN_MINUTES = 15


def _latest_completed_resume(candidate):
    # Same choice of resume as the manual "Score resume" endpoint.
    return candidate.resume_documents.filter(
        processing_status=ResumeProcessingStatus.COMPLETED
    ).order_by("-processed_at", "-created_at").first()


def awaiting_scoring_queryset():
    """Candidates whose newest resume is ready but not yet scored (resume-level check in `_unscored_resume`)."""
    has_active_run = WorkflowRun.objects.filter(candidate=OuterRef("pk"), status__in=ACTIVE_WORKFLOW_STATUSES)
    has_completed_resume = ResumeDocument.objects.filter(
        candidate=OuterRef("pk"), processing_status=ResumeProcessingStatus.COMPLETED
    )
    return (
        Candidate.objects.filter(
            current_status=CandidateStatus.RESUME_RECEIVED,
            requisition__status=RequisitionStatus.OPEN,
        )
        .filter(Exists(has_completed_resume))
        .exclude(Exists(has_active_run))
        .order_by("created_at")
    )


def _unscored_resume(candidate, retry_failed=False):
    resume = _latest_completed_resume(candidate)
    if resume is None:
        return None
    runs = WorkflowRun.objects.filter(resume_document=resume)
    if retry_failed:  # operator recovery after an outage/config fix: resumes whose runs all failed qualify again
        runs = runs.exclude(status=WorkflowRunStatus.FAILED)
    return None if runs.exists() else resume


def count_awaiting_scoring(candidates=None):
    queryset = awaiting_scoring_queryset()
    if candidates is not None:
        queryset = queryset.filter(pk__in=candidates.values("pk"))
    return sum(1 for candidate in queryset if _unscored_resume(candidate) is not None)


def extract_pending_resumes(limit):
    ids = list(
        ResumeDocument.objects.filter(processing_status=ResumeProcessingStatus.PENDING)
        .order_by("created_at")
        .values_list("pk", flat=True)[:limit]
    )
    # Atomic PENDING claim inside the service makes this safe alongside other workers; failures stay visible for retry.
    return process_documents_parallel(ids)


def release_stale_runs(now):
    cutoff = now - timedelta(minutes=STALE_RUN_MINUTES)
    released = 0
    stale = WorkflowRun.objects.filter(
        status__in=(WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING), updated_at__lt=cutoff
    )
    for run in stale:
        claimed = WorkflowRun.objects.filter(pk=run.pk, status=run.status, updated_at=run.updated_at).update(
            status=WorkflowRunStatus.FAILED,
            current_step="FAILED",
            error_code="WORKFLOW_STALE",
            error_message="The scoring workflow stopped before finishing (the worker may have restarted). Score the resume again.",
            updated_at=now,
        )
        if claimed:
            CandidateEvent.objects.create(
                candidate_id=run.candidate_id,
                actor=None,
                event_type=CandidateEvent.EventType.WORKFLOW_FAILED,
                details={"workflow_run_id": str(run.public_id), "error_code": "WORKFLOW_STALE", "trigger": run.trigger},
            )
            released += 1
    return released


def _start_automatic_run(candidate, resume):
    try:
        with transaction.atomic():
            run = WorkflowRun.objects.create(
                candidate=candidate,
                resume_document=resume,
                status=WorkflowRunStatus.PENDING,
                created_by=None,
                trigger=WorkflowTrigger.AUTOMATIC,
            )
    except IntegrityError:
        # A recruiter or another worker started a run for this candidate in the meantime.
        return None
    return start_scoring_workflow(run)


def run_auto_scoring_cycle(limit=None, now=None, retry_failed=False):
    limit = limit or settings.AUTO_SCORING_BATCH_LIMIT
    now = now or timezone.now()
    summary = {
        "extracted": extract_pending_resumes(limit),
        "released_stale": release_stale_runs(now),
        "started": 0,
        "scored": 0,
        "failed": 0,
    }
    for candidate in awaiting_scoring_queryset().select_related("requisition"):
        if summary["started"] >= limit:
            break
        resume = _unscored_resume(candidate, retry_failed=retry_failed)
        if resume is None:
            continue
        run = _start_automatic_run(candidate, resume)
        if run is None:
            continue
        summary["started"] += 1
        if run.status == WorkflowRunStatus.WAITING_HR_REVIEW:
            summary["scored"] += 1
        else:
            summary["failed"] += 1
    logger.info(
        "Automatic scoring cycle: extracted=%s released_stale=%s started=%s scored=%s failed=%s",
        summary["extracted"], summary["released_stale"], summary["started"], summary["scored"], summary["failed"],
    )
    return summary
