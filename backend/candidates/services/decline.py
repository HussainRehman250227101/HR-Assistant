"""Declined candidates: a friendly rejection email, then automatic deletion of their data (name kept).

Trigger: HR's DECLINE decision (shortlist review or screening review) records a `REJECTION_PENDING` marker event and
queues `candidates.tasks.process_declined_candidate`; a beat sweep retries anything still pending. Only candidates with
that marker are processed, so candidates closed any other way (a manual closure) or declined before this feature are
never emailed or erased automatically.

Order matters: the email is sent first, and the data is erased only after the email backend has accepted it, so the
email's statement that the data was deleted is true when the candidate reads it. A candidate with no email address
cannot be notified and is erased straight away. A send failure keeps the data and is retried (up to
`REJECTION_MAX_EMAIL_ATTEMPTS`); after that it stays visible on the dashboard as a failed email.

What is erased is defined by `erase_personal_data(keep_name=True)`: resume files and text, contact details, evidence
excerpts, transcripts and answers, email bodies. The name, statuses, decisions, timestamps and model versions remain.
"""

import logging

from django.conf import settings
from django.db.models import Exists, OuterRef

from ..models import Candidate, CandidateEvent, CandidateStatus
from .privacy import PrivacyError, erase_personal_data
from .status import record_event

logger = logging.getLogger(__name__)
EVENT = CandidateEvent.EventType

ERASURE_REASON = "Declined candidate: automatic deletion after the rejection notice"


class DeclineOutcome:
    ERASED = "ERASED"
    EMAIL_FAILED = "EMAIL_FAILED"
    WAITING = "WAITING"
    SKIPPED = "SKIPPED"


def mark_declined(candidate, actor, source):
    """Record that HR declined this candidate and that the rejection notice + deletion are queued."""
    if settings.REJECTION_AUTO_ENABLED:
        record_event(candidate, actor, EVENT.REJECTION_PENDING, source=source)


def process_declined_candidate(candidate_id):
    from communications.services import CommunicationError, send_rejection_email
    from workflows.models import WorkflowRun, WorkflowRunStatus

    if not settings.REJECTION_AUTO_ENABLED:
        return DeclineOutcome.SKIPPED
    candidate = Candidate.objects.select_related("requisition").filter(pk=candidate_id).first()
    if candidate is None or candidate.current_status != CandidateStatus.CLOSED or candidate.personal_data_erased_at:
        return DeclineOutcome.SKIPPED
    marker = CandidateEvent.objects.filter(candidate=candidate, event_type=EVENT.REJECTION_PENDING).order_by("-created_at").first()
    if marker is None:
        return DeclineOutcome.SKIPPED
    if WorkflowRun.objects.filter(candidate=candidate, status__in=(WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING)).exists():
        return DeclineOutcome.WAITING  # let the scoring workflow finish before the data goes away
    actor = marker.actor
    if candidate.email:
        try:
            sent = send_rejection_email(candidate, actor)
        except CommunicationError:
            sent = False
        if not sent:
            return DeclineOutcome.EMAIL_FAILED
    else:
        record_event(candidate, None, EVENT.REJECTION_EMAIL_SKIPPED, reason="no_email_address")
    try:
        erase_personal_data(candidate, actor, ERASURE_REASON, keep_name=True)
    except PrivacyError:
        return DeclineOutcome.SKIPPED  # erased concurrently by another worker
    return DeclineOutcome.ERASED


def safe_process_declined(candidate_id):
    """Run `process_declined_candidate`; an unexpected error is logged (type only) and retried by the sweep."""
    try:
        return process_declined_candidate(candidate_id)
    except Exception as exc:
        logger.error("Declined-candidate processing failed. exception_type=%s", type(exc).__name__)
        return DeclineOutcome.SKIPPED


def declined_awaiting_processing():
    """Closed candidates with a REJECTION_PENDING marker that are not erased and have attempts left."""
    from communications.models import CommunicationLog, MessageKind

    marker = CandidateEvent.objects.filter(candidate=OuterRef("pk"), event_type=EVENT.REJECTION_PENDING)
    exhausted = CommunicationLog.objects.filter(
        candidate=OuterRef("pk"), kind=MessageKind.REJECTION, send_attempts__gte=settings.REJECTION_MAX_EMAIL_ATTEMPTS,
    )
    return (
        Candidate.objects.filter(current_status=CandidateStatus.CLOSED, personal_data_erased_at__isnull=True)
        .filter(Exists(marker)).exclude(Exists(exhausted)).order_by("updated_at")
    )
