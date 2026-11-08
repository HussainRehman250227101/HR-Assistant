"""Idempotent, database-backed resume extraction processing."""

import logging

from django.utils import timezone

from ..models import CandidateEvent, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from .contact_details import fill_candidate_details_from_resume
from .extraction import ResumeExtractionError, extract_resume_text

logger = logging.getLogger(__name__)


def _record_review_state(document, error_code, error_message, actor=None, failed=False):
    document.processing_status = ResumeProcessingStatus.FAILED if failed else ResumeProcessingStatus.NEEDS_MANUAL_REVIEW
    document.error_code = error_code
    document.error_message = error_message
    document.processed_at = timezone.now()
    document.save(update_fields=("processing_status","error_code","error_message","processed_at"))
    candidate = document.candidate
    previous = candidate.current_status
    if previous == CandidateStatus.RESUME_RECEIVED:
        candidate.current_status = CandidateStatus.NEEDS_MANUAL_REVIEW
        candidate.save(update_fields=("current_status","updated_at"))
    CandidateEvent.objects.create(
        candidate=candidate, actor=actor,
        event_type=CandidateEvent.EventType.RESUME_EXTRACTION_FAILED if failed else CandidateEvent.EventType.RESUME_EXTRACTION_REVIEW,
        details={"resume_document_id":str(document.public_id),"error_code":error_code,"candidate_status_changed":previous == CandidateStatus.RESUME_RECEIVED},
    )


def process_resume_document(document, actor=None):
    """Atomically claim a pending item; repeated calls cannot process completed items twice."""
    claimed = ResumeDocument.objects.filter(pk=document.pk,processing_status=ResumeProcessingStatus.PENDING).update(
        processing_status=ResumeProcessingStatus.PROCESSING,
        processing_started_at=timezone.now(), error_code="", error_message="",
    )
    document.refresh_from_db()
    if not claimed:
        return document
    try:
        with document.file.open("rb") as file_obj:
            result = extract_resume_text(file_obj,document.original_filename)
        document.extracted_text = result.text
        document.extraction_metadata = result.metadata
        document.warning_messages = result.warnings
        document.processing_status = ResumeProcessingStatus.COMPLETED
        document.error_code = ""
        document.error_message = ""
        document.processed_at = timezone.now()
        document.save(update_fields=("extracted_text","extraction_metadata","warning_messages","processing_status","error_code","error_message","processed_at"))
        CandidateEvent.objects.create(
            candidate=document.candidate,actor=actor,
            event_type=CandidateEvent.EventType.RESUME_EXTRACTION_COMPLETED,
            details={"resume_document_id":str(document.public_id),"text_characters":len(result.text),"warning_count":len(result.warnings)},
        )
        try:
            # Before scoring: fills name/contact from the resume so HR doesn't type them and scoring can redact them.
            fill_candidate_details_from_resume(document,actor=actor)
        except Exception as exc:
            logger.error("Candidate detail detection failed. document=%s exception_type=%s",document.public_id,type(exc).__name__)
    except ResumeExtractionError as exc:
        _record_review_state(document,exc.code,exc.message,actor=actor)
    except Exception as exc:
        # Never include the resume path, contents, personal details or exception message in logs.
        logger.error("Unexpected resume processing failure. document=%s exception_type=%s",document.public_id,type(exc).__name__)
        _record_review_state(document,"PROCESSING_ERROR","An unexpected processing error occurred. Retry or send this resume for manual review.",actor=actor,failed=True)
    document.refresh_from_db()
    return document


def queue_resume_retry(document,actor=None):
    """Retry transient failures only; content-related manual-review cases require intervention."""
    if document.processing_status != ResumeProcessingStatus.FAILED:
        return False
    updated = ResumeDocument.objects.filter(pk=document.pk,processing_status=ResumeProcessingStatus.FAILED).update(
        processing_status=ResumeProcessingStatus.PENDING,processing_started_at=None,processed_at=None,error_code="",error_message=""
    )
    if updated:
        candidate=document.candidate
        if candidate.current_status == CandidateStatus.NEEDS_MANUAL_REVIEW:
            candidate.current_status=CandidateStatus.RESUME_RECEIVED
            candidate.save(update_fields=("current_status","updated_at"))
            CandidateEvent.objects.create(candidate=candidate,actor=actor,event_type=CandidateEvent.EventType.STATUS_CHANGED,details={"to":CandidateStatus.RESUME_RECEIVED,"reason":"Resume processing retry queued"})
        candidate.events.create(actor=actor,event_type=CandidateEvent.EventType.RESUME_RETRY_QUEUED,details={"resume_document_id":str(document.public_id)})
    return bool(updated)
