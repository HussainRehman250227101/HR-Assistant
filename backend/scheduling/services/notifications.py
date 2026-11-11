"""Emails to interviewers about their interviews (assigned, unassigned, time changed).

The assignment email is sent once per (interview, interviewer): the audit event is the idempotency record, so a
retry or a re-proposal with the same interviewer never duplicates it. A reassignment by HR is an explicit new
trigger (`force=True`). A send failure is recorded and never breaks scheduling. Messages hold no contact details
or resume content, only the candidate's name, the role and a link to the candidate page in the HR app.
"""

import logging
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from candidates.models import CandidateEvent
from candidates.services.status import record_event

logger = logging.getLogger(__name__)
EVENT = CandidateEvent.EventType
ASSIGNED, UNASSIGNED, TIME_CHANGED = "ASSIGNED", "UNASSIGNED", "TIME_CHANGED"


def _already_notified(interview, interviewer):
    events = interview.candidate.events.filter(event_type=EVENT.INTERVIEWER_NOTIFIED)
    return any(
        e.details.get("interview_id") == str(interview.public_id) and e.details.get("interviewer_id") == interviewer.pk
        and e.details.get("kind", ASSIGNED) == ASSIGNED
        for e in events
    )


def _when(interview):
    if not interview.confirmed_start:
        return "The time is still being arranged. You will see it in My Schedule once it is confirmed."
    local = interview.confirmed_start.astimezone(ZoneInfo(interview.timezone))
    return f"{local.strftime('%A, %d %B %Y at %H:%M')} ({interview.timezone}), {interview.duration_minutes} minutes"


def _where(interview):
    if interview.mode == "VIDEO" and interview.contact_whatsapp and not interview.meeting_link:
        return f"WhatsApp video call on {interview.contact_whatsapp}"
    return interview.meeting_link or interview.location or interview.get_mode_display()


def _link(interview):
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/candidates/{interview.candidate.public_id}"


def render_message(kind, interview, interviewer):
    org = settings.SCREENING_ORGANIZATION_NAME
    name = (interview.candidate.full_name or "").strip() or "a candidate"
    role = interview.requisition.title
    first = (interviewer.first_name or interviewer.get_username()).strip()
    sign = f"Thank you,\nThe {org} Recruiting Team"
    if kind == UNASSIGNED:
        return (
            f"Interview reassigned: {name} for {role}",
            f"Hi {first},\n\nThe interview with {name} for the {role} role at {org} has been reassigned to another "
            f"interviewer. You no longer need to attend, and it has been removed from your schedule.\n\n{sign}",
        )
    details = f"When:  {_when(interview)}\nWhere: {_where(interview)}\n\n"
    tail = f"Open the candidate in the HR app to read their details and download their CV:\n{_link(interview)}\n\n"
    if kind == TIME_CHANGED:
        return (
            f"Interview time changed: {name} for {role}",
            f"Hi {first},\n\nThe interview with {name} for the {role} role at {org} has a new time.\n\n{details}{tail}{sign}",
        )
    return (
        f"New candidate assigned to you: {name} for {role}",
        f"Hi {first},\n\n{name} has been assigned to you as the interviewer for the {role} role at {org}.\n\n"
        f"{details}{tail}You can also see all your interviews in My Schedule.\n\n{sign}",
    )


def _send(kind, interview, interviewer, **event_extra):
    """Send one message to `interviewer`. Returns True when the email backend accepted it. Never raises."""
    base = {"interview_id": str(interview.public_id), "interviewer_id": interviewer.pk, "kind": kind, **event_extra}
    try:
        if not interviewer.email:
            record_event(interview.candidate, None, EVENT.INTERVIEWER_NOTIFICATION_FAILED, reason="no_email_address", **base)
            return False
        subject, body = render_message(kind, interview, interviewer)
        sent = EmailMessage(
            subject=subject, body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[interviewer.email],
            connection=get_connection(),
        ).send(fail_silently=False)
        if sent != 1:
            raise RuntimeError("The email backend did not accept the message.")
    except Exception as exc:  # never break scheduling, never claim it was sent
        logger.warning("Interviewer email failed. interview=%s kind=%s exception_type=%s",
                       interview.public_id, kind, type(exc).__name__)
        try:
            record_event(interview.candidate, None, EVENT.INTERVIEWER_NOTIFICATION_FAILED, reason="send_failed", **base)
        except Exception:
            logger.exception("Could not record the interviewer notification failure.")
        return False
    record_event(interview.candidate, None, EVENT.INTERVIEWER_NOTIFIED, automatic=interview.auto_scheduled, **base)
    return True


def notify_interviewer_assigned(interview, force=False):
    interview.refresh_from_db()
    if interview.status == "CANCELLED" or (not force and _already_notified(interview, interview.interviewer)):
        return False
    return _send(ASSIGNED, interview, interview.interviewer)


def notify_interviewer_unassigned(interview, old_interviewer):
    return _send(UNASSIGNED, interview, old_interviewer)


def notify_interview_time_changed(interview):
    return _send(TIME_CHANGED, interview, interview.interviewer)
