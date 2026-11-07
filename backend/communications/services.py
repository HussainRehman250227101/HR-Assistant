"""Invitation drafting, HR approval and idempotent sending (FR-10, FR-11, SRS §14).

A message is sent only after an authorised user explicitly approves it. An atomic claim on
`send_status` plus a conditional unique constraint guarantee at most one sent message per interview,
kind and calendar sequence, so retries and double clicks never produce a duplicate invitation.
Failures keep the draft, record the error and never mark the interview as scheduled.
"""

import logging
import uuid

from django.conf import settings
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.utils import timezone

from candidates.models import CandidateEvent, CandidateStatus
from candidates.services.status import change_candidate_status, record_event
from scheduling.models import Interview, InterviewStatus
from .models import ApprovalStatus, CommunicationLog, MessageKind, SendStatus
from .templates_text import TEMPLATE_VERSION, build_ics, render, required_field_problems

logger = logging.getLogger(__name__)
EVENT = CandidateEvent.EventType


class CommunicationError(ValueError):
    pass


def kind_for(interview):
    if interview.status == InterviewStatus.CANCELLED:
        return MessageKind.INTERVIEW_CANCELLATION
    if interview.status != InterviewStatus.SLOT_CONFIRMED:
        raise CommunicationError("An invitation can only be drafted once a slot is confirmed with both parties.")
    return MessageKind.INTERVIEW_RESCHEDULE if interview.sequence > 0 else MessageKind.INTERVIEW_INVITATION


def draft_message(interview, actor, kind=None):
    """Return the open draft for this interview/kind/sequence, creating it if needed (idempotent)."""
    kind = kind or kind_for(interview)
    candidate = interview.candidate
    if not candidate.email:
        raise CommunicationError("The candidate has no email address. Add one before drafting the invitation.")
    if kind == MessageKind.INTERVIEW_CANCELLATION and not interview.confirmed_start:
        raise CommunicationError("No invitation was sent for this interview, so no cancellation notice is needed.")
    existing = CommunicationLog.objects.filter(interview=interview, kind=kind, sequence=interview.sequence).exclude(
        approval_status=ApprovalStatus.DISCARDED).first()
    if existing:
        return existing
    subject, body, details = render(kind, interview, candidate)
    count = CommunicationLog.objects.filter(interview=interview, kind=kind, sequence=interview.sequence).count()
    log = CommunicationLog.objects.create(
        candidate=candidate, interview=interview, kind=kind, template_version=TEMPLATE_VERSION,
        sequence=interview.sequence, idempotency_key=f"{interview.public_id}:{kind}:{interview.sequence}:{count}",
        recipient=candidate.email, cc=[interview.interviewer.email] if interview.interviewer.email else [],
        subject=subject, body=body, meeting_details=details, created_by=actor,
    )
    record_event(candidate, actor, EVENT.INVITATION_DRAFTED, communication_id=str(log.public_id), kind=kind,
                 template_version=TEMPLATE_VERSION)
    return log


def update_draft(log, subject, body):
    if log.approval_status != ApprovalStatus.DRAFT:
        raise CommunicationError("Only drafts can be edited.")
    log.subject, log.body = subject.strip(), body.strip()
    log.save(update_fields=("subject", "body", "updated_at"))
    return log


def discard_draft(log, actor):
    if log.approval_status != ApprovalStatus.DRAFT:
        raise CommunicationError("Only unapproved drafts can be discarded.")
    log.approval_status = ApprovalStatus.DISCARDED
    log.save(update_fields=("approval_status", "updated_at"))
    return log


def _check_still_valid(log):
    interview = log.interview
    if interview is None:
        raise CommunicationError("This message is not linked to an interview.")
    if log.sequence != interview.sequence:
        raise CommunicationError("The interview changed after this draft was created. Draft a new message.")
    if log.kind == MessageKind.INTERVIEW_CANCELLATION:
        if interview.status != InterviewStatus.CANCELLED:
            raise CommunicationError("The interview is no longer cancelled.")
    elif interview.status != InterviewStatus.SLOT_CONFIRMED:
        raise CommunicationError("The interview slot is no longer confirmed. Re-confirm a slot and draft again.")
    if log.kind != MessageKind.INTERVIEW_CANCELLATION and interview.confirmed_start <= timezone.now():
        raise CommunicationError("The confirmed slot is in the past. Re-propose a slot.")
    missing = required_field_problems(log)
    if missing:
        raise CommunicationError(f"The email body no longer contains required details: {', '.join(missing)}.")


def approve_and_send(log, actor, connection=None):
    """Record explicit HR approval, then send exactly once. Retries are allowed only after a failure."""
    if log.approval_status == ApprovalStatus.DISCARDED:
        raise CommunicationError("This draft was discarded.")
    if log.send_status == SendStatus.SENT:
        raise CommunicationError("This message has already been sent.")
    if log.send_status == SendStatus.SENDING:
        raise CommunicationError("This message is already being sent.")
    _check_still_valid(log)
    now = timezone.now()
    with transaction.atomic():
        claimed = CommunicationLog.objects.filter(
            pk=log.pk, send_status__in=(SendStatus.NOT_SENT, SendStatus.FAILED),
        ).exclude(approval_status=ApprovalStatus.DISCARDED).update(send_status=SendStatus.SENDING, updated_at=now)
        if not claimed:
            raise CommunicationError("This message is already being sent or was sent.")
        log.refresh_from_db()
        if log.approval_status == ApprovalStatus.DRAFT:
            log.approval_status = ApprovalStatus.APPROVED
            log.approved_by, log.approved_at = actor, now
            log.save(update_fields=("approval_status", "approved_by", "approved_at", "updated_at"))
            record_event(log.candidate, actor, EVENT.INVITATION_APPROVED, communication_id=str(log.public_id), kind=log.kind)

    message_id = f"<{uuid.uuid4().hex}@{settings.INVITATION_MESSAGE_ID_DOMAIN}>"
    email = EmailMessage(
        subject=log.subject, body=log.body, from_email=settings.DEFAULT_FROM_EMAIL, to=[log.recipient], cc=log.cc,
        headers={"Message-ID": message_id, "X-HR-Communication-Id": str(log.public_id)},
        connection=connection or get_connection(),
    )
    email.attach("interview.ics", build_ics(log.interview, log, now),
                 f"text/calendar; method={'CANCEL' if log.kind == MessageKind.INTERVIEW_CANCELLATION else 'REQUEST'}")
    log.send_attempts += 1
    log.provider = settings.EMAIL_BACKEND.rsplit(".", 1)[-1]
    try:
        sent = email.send(fail_silently=False)
        if sent != 1:
            raise RuntimeError("The email backend did not accept the message.")
    except Exception as exc:  # any provider failure: keep the draft, never claim success
        logger.warning("Invitation send failed. communication=%s exception_type=%s", log.public_id, type(exc).__name__)
        log.send_status = SendStatus.FAILED
        log.error_code = "EMAIL_SEND_FAILED"
        log.error_message = "The email provider did not accept the message. The draft is kept; check email settings and retry."
        log.save(update_fields=("send_status", "send_attempts", "provider", "error_code", "error_message", "updated_at"))
        record_event(log.candidate, actor, EVENT.INVITATION_SEND_FAILED, communication_id=str(log.public_id), kind=log.kind)
        raise CommunicationError(log.error_message) from exc

    with transaction.atomic():
        log.send_status = SendStatus.SENT
        log.provider_message_id = message_id
        log.sent_at = timezone.now()
        log.error_code = log.error_message = ""
        log.save(update_fields=("send_status", "send_attempts", "provider", "provider_message_id", "sent_at",
                                "error_code", "error_message", "updated_at"))
        record_event(log.candidate, actor, EVENT.INVITATION_SENT, communication_id=str(log.public_id), kind=log.kind,
                     provider_message_id=message_id)
        if log.kind != MessageKind.INTERVIEW_CANCELLATION:
            Interview.objects.filter(pk=log.interview_id).update(status=InterviewStatus.SCHEDULED, updated_at=log.sent_at)
            change_candidate_status(log.candidate, CandidateStatus.INTERVIEW_SCHEDULED, actor,
                                    "Interview invitation approved and sent", communication_id=str(log.public_id))
    return log
