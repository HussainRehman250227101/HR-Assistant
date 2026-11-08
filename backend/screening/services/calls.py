"""Screening lifecycle: creation, safeguarded outbound calls, result sync, analysis and manual results.

Safeguards (SRS §8, §13, §14): only recruiter-approved candidates, +92 destinations, consent/opt-out
checks, calling-hours window, attempt limits with a minimum retry interval, one active screening per
candidate and an atomic claim so retries or duplicate clicks never place a second concurrent call.

Telephone calls run only when SCREENING_VOICE_MODE=telephony. Browser voice sessions (the default AI
route, no phone call) live in `services/browser.py` and reuse the analysis and escalation helpers here.
"""

import logging
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from candidates.models import CandidateEvent, CandidateStatus, ConsentStatus
from candidates.services.status import change_candidate_status, record_event
from llm.exceptions import LLMConfigurationError, LLMProviderError
from requisitions.models import RequisitionStatus
from .. import script
from ..models import (
    ACTIVE_SCREENING_STATUSES, AI_SCREENING_CHANNELS, CallAttemptStatus, CallOutcome, NextStepRecommendation,
    Screening, ScreeningCallAttempt, ScreeningChannel, ScreeningConsent, ScreeningStatus,
)
from .analysis import PROMPT_VERSION, STRUCTURED_ANSWER_FIELDS, analyze_transcript
from .phone import mask_phone, validate_destination
from .voice import PROVIDER_NAME, VoiceConfigurationError, VoiceProviderError, get_browser_voice_client, get_voice_client

logger = logging.getLogger(__name__)

EVENT = CandidateEvent.EventType
IN_PROGRESS_PROVIDER_STATES = {"initiated", "in-progress", "processing"}
TWILIO_UNANSWERED = {"no-answer": CallOutcome.NO_ANSWER, "busy": CallOutcome.BUSY,
                     "failed": CallOutcome.FAILED, "canceled": CallOutcome.FAILED}
TWILIO_ACTIVE = {"queued", "initiated", "ringing", "in-progress"}


class ScreeningError(ValueError):
    pass


def telephony_enabled():
    return settings.SCREENING_VOICE_MODE == "telephony"


def ai_screening_channel():
    """The AI voice route for the configured mode: a browser session by default, a phone call in telephony mode."""
    return ScreeningChannel.AI_VOICE if telephony_enabled() else ScreeningChannel.BROWSER_VOICE


TELEPHONY_DISABLED_MESSAGE = (
    "Telephone screening calls are disabled (SCREENING_VOICE_MODE=browser). "
    "Use a browser voice session or a human-led screening."
)


def automated_call_blocker(candidate):
    """Return a reason the candidate must not receive an automated call, or None."""
    if candidate.contact_consent_status == ConsentStatus.DECLINED:
        return "The candidate has declined contact."
    if (candidate.consent_preferences or {}).get("automated_call_opt_out"):
        return "The candidate opted out of automated calls. Use a human-led screening instead."
    if candidate.recording_consent_status == ConsentStatus.DECLINED:
        return "The candidate declined call recording. Use a human-led screening instead."
    return None


def within_calling_window(now=None):
    local = (now or timezone.now()).astimezone(ZoneInfo(settings.SCREENING_CALL_TIMEZONE))
    return settings.SCREENING_CALL_WINDOW_START_HOUR <= local.hour < settings.SCREENING_CALL_WINDOW_END_HOUR


def create_screening(candidate, actor, channel):
    requisition = candidate.requisition
    if candidate.current_status != CandidateStatus.APPROVED_FOR_SCREENING:
        raise ScreeningError("Only candidates approved for screening by a recruiter can be screened.")
    if requisition.status != RequisitionStatus.OPEN:
        raise ScreeningError("Screening is only available for open requisitions.")
    questions = [q for q in (requisition.screening_questions or []) if q.strip()]
    if not questions:
        raise ScreeningError("Add approved screening questions to the requisition before screening.")
    if script.AVAILABILITY_QUESTION.casefold() not in {q.strip().casefold() for q in questions}:
        questions.append(script.AVAILABILITY_QUESTION)  # needed for automatic interview scheduling
    if channel == ScreeningChannel.AI_VOICE and not telephony_enabled():
        raise ScreeningError(TELEPHONY_DISABLED_MESSAGE)
    if channel in AI_SCREENING_CHANNELS:
        blocker = automated_call_blocker(candidate)
        if blocker:
            raise ScreeningError(blocker)
    if channel == ScreeningChannel.AI_VOICE:
        try:
            validate_destination(candidate.phone)
        except ValueError as exc:
            raise ScreeningError(str(exc)) from exc
    with transaction.atomic():
        if Screening.objects.select_for_update().filter(candidate=candidate, status__in=ACTIVE_SCREENING_STATUSES).exists():
            raise ScreeningError("This candidate already has an active screening.")
        screening = Screening.objects.create(
            candidate=candidate, requisition=requisition, channel=channel,
            status=ScreeningStatus.PENDING_CALL if channel in AI_SCREENING_CHANNELS else ScreeningStatus.AWAITING_MANUAL_RESULT,
            questions=questions,
            script_version=script.BROWSER_SCRIPT_VERSION if channel == ScreeningChannel.BROWSER_VOICE else script.SCRIPT_VERSION,
            max_attempts=settings.SCREENING_MAX_CALL_ATTEMPTS, created_by=actor,
        )
        record_event(candidate, actor, EVENT.SCREENING_CREATED, screening_id=str(screening.public_id),
                     channel=channel, script_version=screening.script_version)
        change_candidate_status(candidate, CandidateStatus.SCREENING_SCHEDULED_PENDING, actor,
                                "Screening created", screening_id=str(screening.public_id))
    return screening


def _escalate(screening, actor, summary, recommendation):
    screening.status = ScreeningStatus.AWAITING_HR_REVIEW
    screening.recommended_next_step_for_human_review = recommendation
    if not screening.concise_summary:
        screening.concise_summary = summary
    screening.next_attempt_not_before = None
    screening.save()
    record_event(screening.candidate, actor, EVENT.SCREENING_ESCALATED, screening_id=str(screening.public_id),
                 call_status=screening.call_status, reason=summary)
    change_candidate_status(screening.candidate, CandidateStatus.SCREENING_COMPLETED_HR_REVIEW, actor,
                            "Screening requires HR review", screening_id=str(screening.public_id))


def _after_unanswered(screening, actor, outcome, now):
    """Schedule another attempt within limits, or hand the case to HR (SRS §14 retry policy)."""
    screening.call_status = outcome
    if screening.attempt_count < screening.max_attempts:
        screening.status = ScreeningStatus.PENDING_CALL
        screening.next_attempt_not_before = now + timedelta(minutes=settings.SCREENING_RETRY_INTERVAL_MINUTES)
        screening.save()
        return
    _escalate(
        screening, actor,
        f"No completed call after {screening.attempt_count} attempt(s) (last result: {outcome}). "
        "The retry limit is reached; a recruiter must follow up manually.",
        NextStepRecommendation.HUMAN_FOLLOW_UP_REQUIRED,
    )


def place_call(screening, actor, client=None, now=None):
    now = now or timezone.now()
    client = client or get_voice_client()
    candidate = screening.candidate
    if screening.channel == ScreeningChannel.BROWSER_VOICE:
        raise ScreeningError("This is a browser voice screening; start it from the browser session page. No phone call is placed.")
    if screening.channel != ScreeningChannel.AI_VOICE:
        raise ScreeningError("This is a human-led screening; no automated call can be placed.")
    if not telephony_enabled():
        raise ScreeningError(TELEPHONY_DISABLED_MESSAGE)
    if screening.status != ScreeningStatus.PENDING_CALL:
        raise ScreeningError("This screening is not waiting for a call attempt.")
    if candidate.current_status != CandidateStatus.SCREENING_SCHEDULED_PENDING:
        raise ScreeningError("The candidate is not at the screening-pending stage.")
    if screening.requisition.status != RequisitionStatus.OPEN:
        raise ScreeningError("Calls are only allowed for open requisitions.")
    blocker = automated_call_blocker(candidate)
    if blocker:
        raise ScreeningError(blocker)
    if screening.attempt_count >= screening.max_attempts:
        raise ScreeningError("The maximum number of call attempts has been reached.")
    if screening.next_attempt_not_before and now < screening.next_attempt_not_before:
        raise ScreeningError(
            f"The retry interval has not elapsed. Next attempt allowed after {screening.next_attempt_not_before.isoformat()}."
        )
    if not within_calling_window(now):
        raise ScreeningError(
            f"Calls are only allowed between {settings.SCREENING_CALL_WINDOW_START_HOUR}:00 and "
            f"{settings.SCREENING_CALL_WINDOW_END_HOUR}:00 ({settings.SCREENING_CALL_TIMEZONE})."
        )
    try:
        destination = validate_destination(candidate.phone)
    except ValueError as exc:
        raise ScreeningError(str(exc)) from exc
    if not client.is_configured:
        raise VoiceConfigurationError(
            "Twilio/ElevenLabs calling is not configured on the server. Use a human-led screening or configure the integration."
        )

    # Atomic claim: concurrent requests or retries cannot place a second call for the same attempt.
    claimed = Screening.objects.filter(
        pk=screening.pk, status=ScreeningStatus.PENDING_CALL, attempt_count=screening.attempt_count,
    ).update(status=ScreeningStatus.CALL_IN_PROGRESS, attempt_count=F("attempt_count") + 1, updated_at=now)
    if not claimed:
        raise ScreeningError("Another call attempt is already being placed for this screening.")
    screening.refresh_from_db()
    attempt = ScreeningCallAttempt.objects.create(
        screening=screening, attempt_number=screening.attempt_count, provider=PROVIDER_NAME,
        destination_masked=mask_phone(destination), initiated_by=actor,
    )
    try:
        result = client.start_outbound_call(destination, script.build_dynamic_variables(
            screening, settings.SCREENING_ORGANIZATION_NAME, settings.SCREENING_HUMAN_CONTACT,
        ))
    except (VoiceProviderError, VoiceConfigurationError) as exc:
        attempt.status = CallAttemptStatus.FAILED
        attempt.outcome = CallOutcome.FAILED
        attempt.error_code = "CALL_START_FAILED"
        attempt.error_message = str(exc)[:500]
        attempt.ended_at = now
        attempt.save()
        record_event(candidate, actor, EVENT.SCREENING_CALL_FAILED, screening_id=str(screening.public_id),
                     attempt=attempt.attempt_number, error_code=attempt.error_code)
        _after_unanswered(screening, actor, CallOutcome.FAILED, now)
        raise
    attempt.status = CallAttemptStatus.IN_PROGRESS
    attempt.provider_conversation_id = result.get("conversation_id") or None
    attempt.provider_call_sid = result.get("call_sid") or ""
    attempt.save()
    screening.call_timestamp = screening.call_timestamp or now
    screening.error_code = screening.error_message = ""
    screening.save(update_fields=("call_timestamp", "error_code", "error_message", "updated_at"))
    record_event(candidate, actor, EVENT.SCREENING_CALL_STARTED, screening_id=str(screening.public_id),
                 attempt=attempt.attempt_number, destination=attempt.destination_masked)
    return attempt


def _apply_consent_side_effects(screening, actor, result, client):
    candidate = screening.candidate
    prefs = dict(candidate.consent_preferences or {})
    changed = []
    if result["consent_status"] == ScreeningConsent.GRANTED and candidate.recording_consent_status != ConsentStatus.GRANTED:
        candidate.recording_consent_status = ConsentStatus.GRANTED
        changed.append("recording_consent_status")
    if result["consent_status"] == ScreeningConsent.DECLINED:
        candidate.recording_consent_status = ConsentStatus.DECLINED
        prefs["automated_call_opt_out"] = True
        changed += ["recording_consent_status", "consent_preferences"]
    if result["call_outcome"] == CallOutcome.STOPPED_BY_CANDIDATE:
        prefs["automated_call_opt_out"] = True
        changed.append("consent_preferences")
    if not changed:
        return
    candidate.consent_preferences = prefs
    candidate.save(update_fields=tuple(sorted(set(changed))) + ("updated_at",))
    record_event(candidate, actor, EVENT.CONSENT_UPDATED, screening_id=str(screening.public_id),
                 recording_consent_status=candidate.recording_consent_status,
                 automated_call_opt_out=bool(prefs.get("automated_call_opt_out")))
    if result["consent_status"] == ScreeningConsent.DECLINED:
        # Recording consent refused: keep only the outcome, discard transcript locally and at the provider.
        screening.transcript = []
        attempt = screening.call_attempts.exclude(provider_conversation_id=None).order_by("-attempt_number").first()
        if attempt and client is not None:
            try:
                client.delete_conversation(attempt.provider_conversation_id)
                attempt.provider_data_deleted = True
                attempt.save(update_fields=("provider_data_deleted",))
            except (VoiceProviderError, VoiceConfigurationError):
                screening.analysis_warnings = list(screening.analysis_warnings) + [
                    "Consent was declined but the provider conversation could not be deleted automatically. Delete it in ElevenLabs."
                ]


def run_analysis(screening, actor=None, provider=None, client=None):
    """Analyze the stored transcript; on failure keep it so HR can retry (no repeat call needed)."""
    try:
        result, warnings, model_version = analyze_transcript(screening, screening.transcript, provider=provider)
    except (LLMConfigurationError, LLMProviderError, ValueError) as exc:
        logger.warning("Screening analysis failed. screening=%s exception_type=%s", screening.public_id, type(exc).__name__)
        screening.status = ScreeningStatus.ANALYSIS_FAILED
        screening.error_code = "ANALYSIS_FAILED"
        screening.error_message = "The call transcript was saved but could not be summarised. Retry the analysis."
        screening.save()
        record_event(screening.candidate, actor, EVENT.SCREENING_ANALYSIS_FAILED, screening_id=str(screening.public_id))
        return screening
    latest_attempt = screening.call_attempts.order_by("-attempt_number").first()
    if latest_attempt and latest_attempt.outcome == CallOutcome.INTERRUPTED:
        # A dropped browser session must never be presented as a normally completed screening.
        warnings = list(warnings) + [
            "The browser voice session was interrupted (connection lost or provider failure); the transcript may be incomplete."
        ]
        if result["call_outcome"] == CallOutcome.COMPLETED:
            result["call_outcome"] = CallOutcome.INTERRUPTED
    screening.call_status = result["call_outcome"]
    screening.consent_status = result["consent_status"]
    screening.ai_disclosure_confirmed = result["ai_disclosure_given"]
    for field in ("question_answer_pairs", "role_requirement_responses", "candidate_questions",
                  "unresolved_questions", "concise_summary", "recommended_next_step_for_human_review",
                  *STRUCTURED_ANSWER_FIELDS):
        setattr(screening, field, result[field])
    screening.analysis_warnings = warnings
    screening.analysis_provider = "azure_openai"
    screening.analysis_model_version = model_version
    screening.analysis_prompt_version = PROMPT_VERSION
    screening.error_code = screening.error_message = ""
    screening.status = ScreeningStatus.AWAITING_HR_REVIEW
    screening.next_attempt_not_before = None
    with transaction.atomic():
        _apply_consent_side_effects(screening, actor, result, client)
        screening.save()
        record_event(screening.candidate, actor, EVENT.SCREENING_RESULT_RECORDED, screening_id=str(screening.public_id),
                     call_status=screening.call_status, consent_status=screening.consent_status,
                     recommendation=screening.recommended_next_step_for_human_review)
        change_candidate_status(screening.candidate, CandidateStatus.SCREENING_COMPLETED_HR_REVIEW, actor,
                                "Screening result ready for HR review", screening_id=str(screening.public_id))
    return screening


def normalize_transcript(conversation):
    """Provider transcript -> [{role, message, time_in_call_secs}], dropping empty turns."""
    return [
        {"role": "user" if t.get("role") == "user" else "agent", "message": (t.get("message") or "").strip(),
         "time_in_call_secs": t.get("time_in_call_secs")}
        for t in (conversation.get("transcript") or []) if (t.get("message") or "").strip()
    ]


def sync_attempt(attempt, client=None, provider=None, now=None):
    """Fetch provider state for an in-progress call and conclude it once the call has ended. Idempotent."""
    if attempt.screening.channel == ScreeningChannel.BROWSER_VOICE:
        # Browser sessions have no Twilio leg; conclude them from the ElevenLabs conversation only.
        from .browser import conclude_browser_attempt  # local import: browser.py builds on this module

        conclude_browser_attempt(attempt, client=client, provider=provider, now=now)
        attempt.refresh_from_db()
        return attempt
    now = now or timezone.now()
    client = client or get_voice_client()
    if attempt.status != CallAttemptStatus.IN_PROGRESS:
        return attempt
    screening = attempt.screening
    conversation = client.get_conversation(attempt.provider_conversation_id) if attempt.provider_conversation_id else {}
    provider_status = (conversation.get("status") or "").lower()
    twilio = client.get_twilio_call(attempt.provider_call_sid) if attempt.provider_call_sid else None
    telephony_status = (twilio or {}).get("status", "") or ""
    attempt.provider_status = provider_status[:32]
    attempt.telephony_status = telephony_status[:32]
    attempt.last_synced_at = now
    unanswered = TWILIO_UNANSWERED.get(telephony_status)
    if unanswered is None and (provider_status in IN_PROGRESS_PROVIDER_STATES or (not provider_status and telephony_status in TWILIO_ACTIVE)):
        attempt.save(update_fields=("provider_status", "telephony_status", "last_synced_at"))
        return attempt

    metadata = conversation.get("metadata") or {}
    attempt.termination_reason = str(metadata.get("termination_reason") or "")[:255]
    duration = metadata.get("call_duration_secs") or (twilio or {}).get("duration")
    attempt.duration_seconds = int(duration) if str(duration or "").isdigit() else None
    transcript = normalize_transcript(conversation)
    answered_by = ((twilio or {}).get("answered_by") or "").lower()
    if unanswered is None:
        if answered_by.startswith("machine") or "voicemail" in attempt.termination_reason.lower():
            unanswered = CallOutcome.VOICEMAIL
        elif not any(t["role"] == "user" for t in transcript):
            unanswered = CallOutcome.FAILED if provider_status == "failed" else CallOutcome.NO_ANSWER

    # Only one concurrent sync (poller, webhook, manual) may conclude the attempt.
    concluded = ScreeningCallAttempt.objects.filter(pk=attempt.pk, status=CallAttemptStatus.IN_PROGRESS).update(
        status=CallAttemptStatus.ENDED, outcome=unanswered or CallOutcome.COMPLETED, ended_at=now,
        provider_status=attempt.provider_status, telephony_status=attempt.telephony_status,
        termination_reason=attempt.termination_reason, duration_seconds=attempt.duration_seconds, last_synced_at=now,
    )
    attempt.refresh_from_db()
    if not concluded:
        return attempt
    record_event(screening.candidate, None, EVENT.SCREENING_CALL_ENDED, screening_id=str(screening.public_id),
                 attempt=attempt.attempt_number, outcome=attempt.outcome, duration_seconds=attempt.duration_seconds)
    if unanswered:
        _after_unanswered(screening, None, unanswered, now)
        return attempt
    screening.transcript = transcript
    screening.status = ScreeningStatus.ANALYZING
    screening.save(update_fields=("transcript", "status", "updated_at"))
    run_analysis(screening, actor=None, provider=provider, client=client)
    return attempt


def sync_screening(screening, client=None, provider=None):
    attempt = screening.call_attempts.filter(
        status__in=(CallAttemptStatus.IN_PROGRESS, CallAttemptStatus.INITIATING),
    ).order_by("-attempt_number").first()
    if attempt:
        sync_attempt(attempt, client=client, provider=provider)
    screening.refresh_from_db()
    return screening


def retry_analysis(screening, actor, provider=None):
    claimed = Screening.objects.filter(pk=screening.pk, status=ScreeningStatus.ANALYSIS_FAILED).update(status=ScreeningStatus.ANALYZING)
    if not claimed:
        raise ScreeningError("Only screenings whose analysis failed can be re-analysed.")
    screening.refresh_from_db()
    client = get_browser_voice_client() if screening.channel == ScreeningChannel.BROWSER_VOICE else get_voice_client()
    return run_analysis(screening, actor=actor, provider=provider, client=client)


def record_manual_result(screening, actor, data):
    """Human-led alternative screening (SRS §13: alternative route when automated calls are declined)."""
    if screening.channel != ScreeningChannel.HUMAN_LED or screening.status != ScreeningStatus.AWAITING_MANUAL_RESULT:
        raise ScreeningError("This screening is not waiting for a human-led result.")
    answers = {item["question_number"]: item for item in data["question_answer_pairs"]}
    pairs, unresolved = [], list(data.get("unresolved_questions") or [])
    for number, question in enumerate(screening.questions, start=1):
        item = answers.get(number) or {}
        status = item.get("answer_status", "NOT_ASKED")
        statement = (item.get("candidate_statement") or "").strip()
        if status == "ANSWERED" and not statement:
            status = "UNCLEAR"
        if status == "UNCLEAR" and question not in unresolved:
            unresolved.append(question)
        pairs.append({"question_number": number, "question": question, "answer_status": status,
                      "candidate_statement": statement, "agent_interpretation": (item.get("recruiter_note") or "").strip()})
    now = timezone.now()
    with transaction.atomic():
        claimed = Screening.objects.filter(pk=screening.pk, status=ScreeningStatus.AWAITING_MANUAL_RESULT).update(
            status=ScreeningStatus.AWAITING_HR_REVIEW)
        if not claimed:
            raise ScreeningError("This result has already been recorded.")
        screening.refresh_from_db()
        screening.status = ScreeningStatus.AWAITING_HR_REVIEW
        screening.call_status = data["call_status"]
        screening.consent_status = data["consent_status"]
        screening.question_answer_pairs = pairs
        screening.candidate_stated_availability = data.get("candidate_stated_availability", "").strip()
        # Standard answers noted by the recruiter (no transcript, so there are no verified quotes).
        low, high = data.get("expected_salary_min"), data.get("expected_salary_max")
        screening.expected_salary_min, screening.expected_salary_max = (low or high), (high or low)
        stated = low is not None or high is not None
        screening.expected_salary_currency = data.get("expected_salary_currency", "").strip().upper() if stated else ""
        screening.expected_salary_period = data.get("expected_salary_period", "") if stated else ""
        screening.notice_period = data.get("notice_period", "").strip()
        screening.candidate_questions = data.get("candidate_questions") or []
        screening.unresolved_questions = unresolved
        screening.concise_summary = data["concise_summary"].strip()
        screening.recommended_next_step_for_human_review = NextStepRecommendation.REVIEW_FOR_INTERVIEW_DECISION
        screening.call_timestamp = data.get("call_timestamp") or now
        screening.result_recorded_by = actor
        screening.result_recorded_at = now
        screening.save()
        record_event(screening.candidate, actor, EVENT.SCREENING_RESULT_RECORDED, screening_id=str(screening.public_id),
                     channel=screening.channel, call_status=screening.call_status)
        change_candidate_status(screening.candidate, CandidateStatus.SCREENING_COMPLETED_HR_REVIEW, actor,
                                "Human-led screening recorded", screening_id=str(screening.public_id))
    return screening


def cancel_screening(screening, actor, reason):
    if screening.status in {ScreeningStatus.CALL_IN_PROGRESS, ScreeningStatus.ANALYZING}:
        raise ScreeningError("A call or browser session is in progress. Check its result before cancelling.")
    if screening.status not in {ScreeningStatus.PENDING_CALL, ScreeningStatus.AWAITING_MANUAL_RESULT, ScreeningStatus.ANALYSIS_FAILED}:
        raise ScreeningError("Only pending screenings can be cancelled. Completed screenings are handled in screening review.")
    with transaction.atomic():
        screening.status = ScreeningStatus.CANCELLED
        screening.error_message = ""
        screening.save()
        record_event(screening.candidate, actor, EVENT.SCREENING_CANCELLED, screening_id=str(screening.public_id), reason=reason)
        change_candidate_status(screening.candidate, CandidateStatus.APPROVED_FOR_SCREENING, actor,
                                f"Screening cancelled: {reason}", screening_id=str(screening.public_id))
    return screening
