"""HR Administrator moves an interview to another interviewer and/or another date and time.

Used mainly before removing a recruiter who still has interviews. In one transaction the interview gets its new
interviewer and slot (never a double booking) and is confirmed again. Afterwards, outside the transaction:
* the candidate gets the invitation / reschedule email (the administrator's action is the approval, like the
  scheduling agent's automatic send), with the updated calendar file;
* the new interviewer gets the assignment email, the old interviewer an "interview reassigned" notice (or the same
  interviewer a "time changed" notice).
Each email result is returned and none is reported as sent unless the email backend accepted it.
"""

import logging
from datetime import datetime, timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from candidates.models import CandidateEvent, CandidateStatus
from candidates.services.status import change_candidate_status, record_event
from communications.services import CommunicationError, approve_and_send, draft_message
from ..models import ACTIVE_INTERVIEW_STATUSES, AvailabilitySlot, InterviewStatus
from .notifications import notify_interview_time_changed, notify_interviewer_assigned, notify_interviewer_unassigned
from .slots import SchedulingError, busy_intervals, get_zone

logger = logging.getLogger(__name__)
EVENT = CandidateEvent.EventType


def reassign_interview(interview, actor, new_interviewer=None, date=None, start_time=None, timezone_name=None):
    """Returns (interview, email_results, outside_declared_availability)."""
    if interview.status not in ACTIVE_INTERVIEW_STATUSES:
        raise SchedulingError("Only an active interview can be reassigned.")
    new_interviewer = new_interviewer or interview.interviewer
    if not new_interviewer.is_active:
        raise SchedulingError("The new interviewer's account is not active.")
    if (date is None) != (start_time is None):
        raise SchedulingError("Give both the new date and the new time.")
    changing_time = date is not None
    changing_person = new_interviewer.pk != interview.interviewer_id
    if not (changing_time or changing_person):
        raise SchedulingError("Choose a different interviewer or a new date and time.")
    if not changing_time and not interview.confirmed_start:
        raise SchedulingError("This interview has no time yet. Give a date and time as well.")

    old_interviewer, old_start = interview.interviewer, interview.confirmed_start
    was_invited = interview.status == InterviewStatus.SCHEDULED
    tz_name = timezone_name or interview.timezone
    zone = get_zone(tz_name)
    start = datetime.combine(date, start_time, tzinfo=zone) if changing_time else old_start
    end = start + timedelta(minutes=interview.duration_minutes)
    if start <= timezone.now():
        raise SchedulingError("The new time must be in the future.")

    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=new_interviewer.pk)
        if any(b_start < end and start < b_end for b_start, b_end in busy_intervals(new_interviewer, exclude=interview)):
            raise SchedulingError("The new interviewer already has an interview at that time.")
        in_availability = AvailabilitySlot.objects.filter(interviewer=new_interviewer, start__lte=start, end__gte=end).exists()
        now = timezone.now()
        interview.interviewer = new_interviewer
        interview.timezone = tz_name
        interview.confirmed_start, interview.confirmed_end = start, end
        interview.candidate_confirmed_at = interview.interviewer_confirmed_at = now
        interview.proposed_slots = [{"start": start.isoformat(), "end": end.isoformat()}]
        if was_invited:
            interview.sequence += 1  # the next message updates the invitation already sent
        interview.status = InterviewStatus.SLOT_CONFIRMED
        interview.save()
        if was_invited and interview.candidate.current_status == CandidateStatus.INTERVIEW_SCHEDULED:
            change_candidate_status(interview.candidate, CandidateStatus.INTERVIEW_PROPOSED, actor,
                                    "Interview reassigned by HR", interview_id=str(interview.public_id))
        record_event(
            interview.candidate, actor, EVENT.INTERVIEW_REASSIGNED, interview_id=str(interview.public_id),
            from_interviewer_id=old_interviewer.pk, to_interviewer_id=new_interviewer.pk,
            from_start=old_start.isoformat() if old_start else None, to_start=start.isoformat(),
            timezone=tz_name, outside_declared_availability=not in_availability,
        )

    results = {"candidate": _email_candidate(interview, actor)}
    if changing_person:
        results["new_interviewer"] = "SENT" if notify_interviewer_assigned(interview, force=True) else "NOT_SENT"
        results["old_interviewer"] = "SENT" if notify_interviewer_unassigned(interview, old_interviewer) else "NOT_SENT"
    else:
        results["interviewer"] = "SENT" if notify_interview_time_changed(interview) else "NOT_SENT"
    interview.refresh_from_db()
    return interview, results, not in_availability


def _email_candidate(interview, actor):
    """Invitation (first time) or reschedule update to the candidate. Returns SENT or NOT_SENT; never raises."""
    try:
        approve_and_send(draft_message(interview, actor), actor, automatic=True)
        return "SENT"
    except CommunicationError:
        logger.warning("Candidate email after reassignment not sent. interview=%s", interview.public_id)
    except Exception as exc:  # provider failure: the draft stays for HR to retry
        logger.warning("Candidate email after reassignment failed. interview=%s exception_type=%s",
                       interview.public_id, type(exc).__name__)
    return "NOT_SENT"
