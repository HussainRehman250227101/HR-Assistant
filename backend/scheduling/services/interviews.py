"""Interview lifecycle up to a confirmed slot. Invitations (Module 13) require separate HR approval."""

from datetime import datetime

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from candidates.models import CandidateEvent, CandidateStatus
from candidates.services.status import change_candidate_status, record_event
from requisitions.models import RequisitionStatus
from ..models import (
    ACTIVE_INTERVIEW_STATUSES, CALENDAR_SOURCE_INTERNAL, Interview, InterviewMode, InterviewStatus,
)
from .slots import SchedulingError, compute_slots, get_zone, is_slot_free

EVENT = CandidateEvent.EventType


def _windows_to_utc(windows):
    return [(datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])) for w in windows]


def _validate_details(mode, meeting_link, location):
    if mode == InterviewMode.VIDEO and not meeting_link:
        raise SchedulingError("A meeting link is required for video interviews.")
    if mode == InterviewMode.ONSITE and not location:
        raise SchedulingError("A location is required for on-site interviews.")


def _apply_proposal(interview, actor):
    slots = compute_slots(interview.interviewer, _windows_to_utc(interview.candidate_windows),
                          interview.duration_minutes, exclude=interview)
    interview.proposed_slots = slots
    interview.calendar_source = CALENDAR_SOURCE_INTERNAL
    interview.status = InterviewStatus.PROPOSED if slots else InterviewStatus.NEEDS_HR_COORDINATION
    if interview.sequence == 0:
        # Before any invitation is sent the tentative slot is simply released. After a sent invitation the
        # last communicated time is kept (it is no longer booked) so a cancellation notice can reference it.
        interview.confirmed_start = interview.confirmed_end = None
    interview.candidate_confirmed_at = interview.interviewer_confirmed_at = None
    interview.save()
    # Audit every calendar check (SRS §13).
    record_event(
        interview.candidate, actor,
        EVENT.INTERVIEW_SLOTS_PROPOSED if slots else EVENT.INTERVIEW_NO_SHARED_AVAILABILITY,
        interview_id=str(interview.public_id), calendar_source=interview.calendar_source,
        slot_count=len(slots), interviewer=interview.interviewer.get_username(),
    )
    return interview


def plan_interview(candidate, actor, data):
    if candidate.current_status != CandidateStatus.APPROVED_FOR_INTERVIEW:
        raise SchedulingError("Only candidates approved for interview by HR can be scheduled.")
    if candidate.requisition.status != RequisitionStatus.OPEN:
        raise SchedulingError("Interviews can only be scheduled for open requisitions.")
    get_zone(data["timezone"])
    _validate_details(data["mode"], data.get("meeting_link", ""), data.get("location", ""))
    with transaction.atomic():
        if Interview.objects.select_for_update().filter(candidate=candidate, status__in=ACTIVE_INTERVIEW_STATUSES).exists():
            raise SchedulingError("This candidate already has an active interview.")
        interview = Interview.objects.create(
            candidate=candidate, requisition=candidate.requisition, interviewer=data["interviewer"],
            duration_minutes=data["duration_minutes"], timezone=data["timezone"], mode=data["mode"],
            meeting_link=data.get("meeting_link", ""), location=data.get("location", ""),
            candidate_availability_note=data.get("candidate_availability_note", ""),
            candidate_windows=data["candidate_windows"], created_by=actor,
        )
        record_event(candidate, actor, EVENT.INTERVIEW_PLANNED, interview_id=str(interview.public_id),
                     duration_minutes=interview.duration_minutes, timezone=interview.timezone)
        _apply_proposal(interview, actor)
        change_candidate_status(candidate, CandidateStatus.INTERVIEW_PROPOSED, actor, "Interview slots being coordinated",
                                interview_id=str(interview.public_id))
    return interview


def repropose(interview, actor, data):
    """Re-run the availability check, optionally with new candidate windows / interviewer / details."""
    if interview.status not in {InterviewStatus.PROPOSED, InterviewStatus.NEEDS_HR_COORDINATION,
                                InterviewStatus.SLOT_CONFIRMED, InterviewStatus.SCHEDULED}:
        raise SchedulingError("This interview can no longer be rescheduled.")
    rescheduling = interview.status == InterviewStatus.SCHEDULED
    for field in ("interviewer", "duration_minutes", "timezone", "mode", "meeting_link", "location",
                  "candidate_availability_note", "candidate_windows"):
        if field in data:
            setattr(interview, field, data[field])
    get_zone(interview.timezone)
    _validate_details(interview.mode, interview.meeting_link, interview.location)
    with transaction.atomic():
        if rescheduling:
            # A sent invitation is superseded: the next message is an update with a higher iCalendar SEQUENCE.
            interview.sequence += 1
            change_candidate_status(interview.candidate, CandidateStatus.INTERVIEW_PROPOSED, actor,
                                    "Interview being rescheduled", interview_id=str(interview.public_id))
        return _apply_proposal(interview, actor)


def confirm_slot(interview, actor, slot_start, candidate_confirmed, interviewer_confirmed):
    """SRS §8: confirm both the candidate's and the interviewer's availability before an invitation is prepared."""
    if interview.status != InterviewStatus.PROPOSED:
        raise SchedulingError("Only proposed slots can be confirmed.")
    if not (candidate_confirmed and interviewer_confirmed):
        raise SchedulingError("Confirm that both the candidate and the interviewer agreed to this slot.")
    slot = next((s for s in interview.proposed_slots if datetime.fromisoformat(s["start"]) == slot_start), None)
    if slot is None:
        raise SchedulingError("The chosen time is not one of the proposed slots.")
    start, end = datetime.fromisoformat(slot["start"]), datetime.fromisoformat(slot["end"])
    if start <= timezone.now():
        raise SchedulingError("This slot is in the past. Re-propose slots.")
    with transaction.atomic():
        # Lock the interviewer row so two confirmations cannot double-book the same slot (PostgreSQL);
        # SQLite serialises write transactions itself.
        get_user_model().objects.select_for_update().get(pk=interview.interviewer_id)
        if not is_slot_free(interview.interviewer, start, end, exclude=interview):
            raise SchedulingError("The slot is no longer available in the interviewer's calendar. Re-propose slots.")
        now = timezone.now()
        interview.confirmed_start, interview.confirmed_end = start, end
        interview.candidate_confirmed_at = interview.interviewer_confirmed_at = now
        interview.status = InterviewStatus.SLOT_CONFIRMED
        interview.save()
        record_event(interview.candidate, actor, EVENT.INTERVIEW_SLOT_CONFIRMED, interview_id=str(interview.public_id),
                     slot_start=start.isoformat(), timezone=interview.timezone)
    return interview


def cancel_interview(interview, actor, reason):
    if interview.status == InterviewStatus.CANCELLED:
        raise SchedulingError("This interview is already cancelled.")
    if not reason.strip():
        raise SchedulingError("A cancellation reason is required.")
    from communications.models import CommunicationLog, SendStatus
    from communications.services import CommunicationError, draft_message

    invitation_sent = CommunicationLog.objects.filter(interview=interview, send_status=SendStatus.SENT).exists()
    was_scheduled = interview.status == InterviewStatus.SCHEDULED
    with transaction.atomic():
        interview.status = InterviewStatus.CANCELLED
        interview.cancellation_reason = reason.strip()
        interview.save()
        record_event(interview.candidate, actor, EVENT.INTERVIEW_CANCELLED, interview_id=str(interview.public_id),
                     reason=interview.cancellation_reason, invitation_was_sent=was_scheduled)
        if interview.candidate.current_status in {CandidateStatus.INTERVIEW_PROPOSED, CandidateStatus.INTERVIEW_SCHEDULED}:
            change_candidate_status(interview.candidate, CandidateStatus.APPROVED_FOR_INTERVIEW, actor,
                                    "Interview cancelled; candidate remains approved for interview",
                                    interview_id=str(interview.public_id))
        if invitation_sent:
            # The candidate already received an invitation: prepare a cancellation notice for HR to approve.
            try:
                draft_message(interview, actor, kind="INTERVIEW_CANCELLATION")
            except CommunicationError:
                pass
    return interview
