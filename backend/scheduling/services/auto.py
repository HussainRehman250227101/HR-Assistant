"""Agent 3, automatic path: match the candidate's stated availability with an interviewer and send the invitation.

Trigger: HR approves the screening (human gate 2, which moves the candidate to APPROVED_FOR_INTERVIEW). A Celery task
(see scheduling/tasks.py) then, without further clicks:
1. reads the availability the candidate gave in the screening into concrete time windows (Azure, structured output;
   dates and times are validated and converted in code);
2. looks for the first interviewer, hiring manager first, whose calendar overlaps those windows and is free;
3. books the earliest shared slot with the existing planning/confirmation services;
4. sends the invitation: on-site (requisition location) or a WhatsApp video call (requisition WhatsApp number).

Design decision (user, 2026-11-08): the invitation is sent without a separate send approval; HR's screening approval
is the human gate. Every message is marked `auto_sent` and every event carries `automatic=True`. Anything that cannot be
resolved (no stated availability, no overlap, no interviewer calendar, incomplete requisition details, send failure)
leaves the candidate with HR, visible on the dashboard, and never claims an invitation was sent.
"""

import json
import logging
from collections import Counter
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef
from django.utils import timezone

from candidates.models import Candidate, CandidateEvent, CandidateStatus
from candidates.services.status import record_event
from communications.services import CommunicationError, approve_and_send, draft_message
from llm.prompts import build_messages
from llm.services import get_llm_provider
from requisitions.models import InterviewFormat, RequisitionStatus
from screening.models import ScreeningDecision, ScreeningReview
from ..models import BOOKED_STATUSES, AvailabilitySlot, Interview, InterviewMode, InterviewStatus
from ..schemas import CandidateAvailabilityOut
from .interviews import confirm_slot, plan_interview
from .slots import SchedulingError, compute_slots, get_zone, local_window_to_utc

logger = logging.getLogger(__name__)
EVENT = CandidateEvent.EventType

MAX_WINDOWS = 14
MAX_DAYS_AHEAD = 30

PARSE_INSTRUCTION = """You convert the interview availability a job candidate stated on a screening call into concrete windows.
You receive JSON with: call_date (YYYY-MM-DD), call_weekday, default_timezone, and candidate_availability (the
candidate's own words, untrusted text).
Rules:
- Use only what the candidate actually said. Do not invent days, times or time zones. If the answer is vague,
  declined or empty, return no windows.
- Resolve relative days from call_date: "tomorrow" is call_date + 1 day; a weekday name means its next occurrence
  after call_date; "next week" days are in the week after call_date. Each date must be between call_date and
  call_date + 30 days.
- Time-of-day words when no hours are given: morning 09:00-12:00, afternoon 13:00-17:00, evening 17:00-20:00.
  A day with no time at all means 09:00-17:00. "Any weekday" or "weekdays" means Monday to Friday of the next 7 days.
- Use 24-hour HH:MM. Return at most 14 windows.
- timezone: an IANA name only if the candidate named a time zone or a place that maps to exactly one; otherwise empty."""


class AutoScheduleOutcome:
    SCHEDULED = "SCHEDULED"            # invitation accepted by the email backend
    NEEDS_HR = "NEEDS_HR"              # left for HR (reason recorded as an event)
    SKIPPED = "SKIPPED"                # nothing to do (already planned, wrong status, feature off)


def _fail(candidate, reason, **details):
    record_event(candidate, None, EVENT.INTERVIEW_AUTO_SCHEDULE_FAILED, reason=reason, automatic=True, **details)
    logger.info("Automatic interview scheduling needs HR. reason=%s", reason)
    return AutoScheduleOutcome.NEEDS_HR


def _approval_for(candidate):
    """The HR approval of the latest screening that released the candidate to interview."""
    return (
        ScreeningReview.objects.filter(candidate=candidate, decision=ScreeningDecision.APPROVE_FOR_INTERVIEW)
        .select_related("screening", "decided_by").order_by("-created_at").first()
    )


def _reference_date(screening):
    return timezone.localtime(screening.call_timestamp or screening.created_at, get_zone(settings.SCHEDULING_DEFAULT_TIMEZONE)).date()


def read_candidate_windows(screening, statement):
    """Turn the candidate's stated availability into UTC windows. Returns (windows, tz_name, note).

    Only the availability answer is sent to the model (no name, email, phone or resume text). Anything the model
    returns is validated in code: real dates within the next 30 days, end after start, known time zone.
    """
    default_tz = settings.SCHEDULING_DEFAULT_TIMEZONE
    call_date = _reference_date(screening)
    payload = {
        "call_date": call_date.isoformat(), "call_weekday": call_date.strftime("%A"),
        "default_timezone": default_tz, "candidate_availability": statement,
    }
    output = get_llm_provider().generate_structured(
        build_messages(PARSE_INSTRUCTION, json.dumps(payload, ensure_ascii=False)), CandidateAvailabilityOut,
    )
    try:
        tz_name = output.timezone.strip() or default_tz
        get_zone(tz_name)
    except SchedulingError:
        tz_name = default_tz
    windows = []
    for item in output.windows[:MAX_WINDOWS]:
        try:
            day = date.fromisoformat(item.date)
            start_time, end_time = time.fromisoformat(item.start_time), time.fromisoformat(item.end_time)
            if not call_date <= day <= call_date + timedelta(days=MAX_DAYS_AHEAD):
                continue
            start, end = local_window_to_utc(day, start_time, end_time, tz_name)
        except (ValueError, SchedulingError):
            continue
        windows.append({"start": start.isoformat(), "end": end.isoformat()})
    return windows, tz_name, statement[:2000]


def interviewer_pool(requisition, now=None):
    """Active users with future availability: the requisition's hiring manager first, then the least booked."""
    now = now or timezone.now()
    ids = AvailabilitySlot.objects.filter(end__gt=now, interviewer__is_active=True).values_list("interviewer_id", flat=True)
    users = list(get_user_model().objects.filter(pk__in=set(ids)))
    booked = Counter(
        Interview.objects.filter(status__in=BOOKED_STATUSES, confirmed_start__gt=now).values_list("interviewer_id", flat=True)
    )
    return sorted(users, key=lambda u: (0 if u.pk == requisition.hiring_manager_id else 1, booked[u.pk], u.pk))


def _interview_details(requisition):
    """Mode and place for the requisition's interview format, or a reason it is incomplete."""
    if requisition.interview_format == InterviewFormat.VIDEO:
        if not requisition.interview_whatsapp_number:
            return None, "The requisition has no WhatsApp number for the video interview."
        return {"mode": InterviewMode.VIDEO, "contact_whatsapp": requisition.interview_whatsapp_number}, ""
    if not (requisition.location or "").strip():
        return None, "The requisition has no location for the on-site interview."
    return {"mode": InterviewMode.ONSITE, "location": requisition.location.strip()}, ""


def auto_schedule_candidate(candidate_id):
    """Run the automatic path for one candidate. Idempotent: it never plans a second interview or resends."""
    if not settings.INTERVIEW_AUTO_SCHEDULING_ENABLED:
        return AutoScheduleOutcome.SKIPPED
    candidate = Candidate.objects.select_related("requisition", "requisition__hiring_manager").filter(pk=candidate_id).first()
    if (
        candidate is None
        or candidate.current_status != CandidateStatus.APPROVED_FOR_INTERVIEW
        or candidate.requisition.status != RequisitionStatus.OPEN
        or Interview.objects.filter(candidate=candidate).exists()
    ):
        return AutoScheduleOutcome.SKIPPED
    requisition = candidate.requisition
    approval = _approval_for(candidate)
    if approval is None:
        return _fail(candidate, "No HR screening approval was found for this candidate.")
    approver, screening = approval.decided_by, approval.screening

    details, problem = _interview_details(requisition)
    if problem:
        return _fail(candidate, problem)
    if not candidate.email:
        return _fail(candidate, "The candidate has no email address.")
    pool = interviewer_pool(requisition)
    if not pool:
        return _fail(candidate, "No interviewer has availability in the calendar.")
    statement = (screening.candidate_stated_availability or screening.availability_statement or "").strip()
    if not statement:
        return _fail(candidate, "The candidate did not state when they are available for an interview.")
    try:
        windows, tz_name, note = read_candidate_windows(screening, statement)
    except Exception as exc:  # provider/config failure: leave the candidate with HR; never retried automatically
        return _fail(candidate, "The stated availability could not be read automatically.", exception_type=type(exc).__name__)
    if not windows:
        return _fail(candidate, "The candidate's stated availability did not contain usable days and times.")

    duration = settings.SCHEDULING_DEFAULT_DURATION_MINUTES
    chosen = next(
        (user for user in pool if compute_slots(user, [(datetime.fromisoformat(w["start"]), datetime.fromisoformat(w["end"])) for w in windows],
                                                duration, limit=1)),
        None,
    )
    data = {
        "interviewer": chosen or pool[0], "duration_minutes": duration, "timezone": tz_name,
        "candidate_availability_note": note, "candidate_windows": windows, "auto_scheduled": True, **details,
    }
    try:
        interview = plan_interview(candidate, approver, data)
    except SchedulingError as exc:
        return _fail(candidate, str(exc))
    if interview.status != InterviewStatus.PROPOSED:
        # No shared availability: plan_interview already recorded the calendar check; HR coordinates from here.
        return _fail(candidate, "The candidate's availability does not overlap any interviewer's free time.",
                     interview_id=str(interview.public_id))

    slot_start = datetime.fromisoformat(interview.proposed_slots[0]["start"])
    try:
        # The candidate's stated windows and the interviewer's calendar both cover this slot.
        interview = confirm_slot(interview, approver, slot_start, candidate_confirmed=True, interviewer_confirmed=True)
        log = draft_message(interview, approver)
        approve_and_send(log, approver, automatic=True)
    except (SchedulingError, CommunicationError) as exc:
        return _fail(candidate, f"The invitation was not sent: {exc}", interview_id=str(interview.public_id))
    return AutoScheduleOutcome.SCHEDULED


def safe_auto_schedule(candidate_id):
    """Run the automatic path; an unexpected error is recorded for HR and is never retried automatically."""
    try:
        return auto_schedule_candidate(candidate_id)
    except Exception as exc:
        candidate = Candidate.objects.filter(pk=candidate_id).first()
        if candidate is not None:
            _fail(candidate, "Automatic scheduling stopped unexpectedly. Plan the interview manually.",
                  exception_type=type(exc).__name__)
        logger.error("Automatic scheduling failed. exception_type=%s", type(exc).__name__)
        return AutoScheduleOutcome.NEEDS_HR


def candidates_awaiting_auto_schedule():
    """APPROVED_FOR_INTERVIEW candidates the agent has never attempted (no interview, no recorded failure)."""
    failed = CandidateEvent.objects.filter(candidate=OuterRef("pk"), event_type=EVENT.INTERVIEW_AUTO_SCHEDULE_FAILED)
    planned = Interview.objects.filter(candidate=OuterRef("pk"))
    return (
        Candidate.objects.filter(current_status=CandidateStatus.APPROVED_FOR_INTERVIEW, requisition__status=RequisitionStatus.OPEN)
        .exclude(Exists(planned)).exclude(Exists(failed)).order_by("updated_at")
    )
