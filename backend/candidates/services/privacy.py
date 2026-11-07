"""Candidate closure, personal-data erasure and retention (SRS §12 Privacy, §13 retention/deletion).

Erasure removes direct identifiers and free text that can contain personal data (resume files and text,
evidence excerpts, transcripts, answers, email bodies) while keeping the non-identifying audit skeleton:
statuses, decisions, timestamps, actors and model versions. It overrides the usual append-only rule
because a deletion request takes precedence over record immutability.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from audit.models import log_audit
from ..models import Candidate, CandidateEvent, CandidateStatus
from .status import change_candidate_status, record_event

logger = logging.getLogger(__name__)
REDACTED_EMAIL = "redacted@example.invalid"


class PrivacyError(ValueError):
    pass


def close_candidate(candidate, actor, reason):
    """Authorised closure with a reason (SRS §9 Closed). Active calls/interviews must be resolved first."""
    from scheduling.models import ACTIVE_INTERVIEW_STATUSES, InterviewStatus
    from screening.models import Screening, ScreeningStatus

    reason = (reason or "").strip()
    if not reason:
        raise PrivacyError("A reason is required to close a candidate.")
    if candidate.current_status == CandidateStatus.CLOSED:
        raise PrivacyError("This candidate is already closed.")
    if Screening.objects.filter(candidate=candidate, status__in=(ScreeningStatus.CALL_IN_PROGRESS, ScreeningStatus.ANALYZING)).exists():
        raise PrivacyError("A screening call is in progress. Wait for it to finish before closing.")
    if candidate.interviews.filter(status=InterviewStatus.SCHEDULED).exists():
        raise PrivacyError("Cancel the scheduled interview first so the candidate receives a cancellation notice.")
    with transaction.atomic():
        candidate.screenings.filter(status__in=(
            ScreeningStatus.PENDING_CALL, ScreeningStatus.AWAITING_MANUAL_RESULT,
            ScreeningStatus.ANALYSIS_FAILED, ScreeningStatus.AWAITING_HR_REVIEW,
        )).update(status=ScreeningStatus.CANCELLED, updated_at=timezone.now())
        candidate.interviews.filter(status__in=ACTIVE_INTERVIEW_STATUSES).update(
            status=InterviewStatus.CANCELLED, cancellation_reason=f"Candidate closed: {reason}", updated_at=timezone.now())
        candidate.closed_reason = reason
        candidate.save(update_fields=("closed_reason", "updated_at"))
        change_candidate_status(candidate, CandidateStatus.CLOSED, actor, reason)
        record_event(candidate, actor, CandidateEvent.EventType.CANDIDATE_CLOSED, reason=reason)
    return candidate


def erase_personal_data(candidate, actor, reason):
    from communications.models import CommunicationLog
    from scoring.models import ResumeEvaluation
    from screening.models import Screening

    if candidate.current_status != CandidateStatus.CLOSED:
        raise PrivacyError("Close the candidate before erasing personal data.")
    if candidate.personal_data_erased_at:
        raise PrivacyError("Personal data was already erased.")
    reason = (reason or "").strip()
    if not reason:
        raise PrivacyError("A reason (e.g. deletion request or retention expiry) is required.")
    files = []
    with transaction.atomic():
        for document in candidate.resume_documents.all():
            if document.file:
                files.append(document.file.name)
            document.file = ""
            document.extracted_text = ""
            document.original_filename = "erased"
            document.extraction_metadata = {}
            document.warning_messages = []
            document.save(update_fields=("file", "extracted_text", "original_filename", "extraction_metadata", "warning_messages"))
        ResumeEvaluation.objects.filter(candidate=candidate).update(evidence={}, overall_assessment="", missing_or_unclear_items=[])
        Screening.objects.filter(candidate=candidate).update(
            transcript=[], question_answer_pairs=[], candidate_stated_availability="", role_requirement_responses=[],
            candidate_questions=[], unresolved_questions=[], concise_summary="[erased]",
        )
        candidate.interviews.update(candidate_availability_note="", candidate_windows=[])
        CommunicationLog.objects.filter(candidate=candidate).update(recipient=REDACTED_EMAIL, cc=[], body="[erased]", meeting_details={})
        candidate.full_name = ""
        candidate.email = None
        candidate.phone = ""
        candidate.location = ""
        candidate.linkedin_url = ""
        candidate.consent_preferences = {"personal_data_erased": True}
        candidate.closed_reason = "[erased]"
        candidate.personal_data_erased_at = timezone.now()
        candidate.save()
        record_event(candidate, actor, CandidateEvent.EventType.PERSONAL_DATA_ERASED, reason=reason, resume_files=len(files))
        log_audit(actor, "CANDIDATE_PERSONAL_DATA_ERASED", "candidate", candidate.public_id, reason=reason)

    def remove_files():
        from django.core.files.storage import default_storage
        for name in files:
            try:
                default_storage.delete(name)
            except OSError as exc:
                logger.warning("Resume file deletion failed. exception_type=%s", type(exc).__name__)

    transaction.on_commit(remove_files)
    return candidate


def expired_candidates(now=None):
    cutoff = (now or timezone.now()) - timedelta(days=settings.CANDIDATE_RETENTION_DAYS)
    return Candidate.objects.filter(current_status=CandidateStatus.CLOSED, personal_data_erased_at__isnull=True, updated_at__lt=cutoff)
