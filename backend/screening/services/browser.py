"""Browser voice screening (Module 16; FR-05, FR-06, FR-07): ElevenLabs Conversational AI over WebRTC.

The HR application opens a voice session in the browser with the official ElevenLabs React SDK. In the
demo, the presenter speaks as the simulated candidate. No telephone call is placed and Twilio is never
contacted.

* Start: requires an explicit disclosure/consent acknowledgement and the usual eligibility checks. It
  atomically claims the next attempt, then mints a short-lived WebRTC conversation token on the server
  (the ElevenLabs API key never reaches the browser). The ElevenLabs conversation ID returned with the
  token is stored on the attempt.
* Complete: the authoritative conversation is fetched from ElevenLabs. A transcript posted by the browser
  is never accepted.
  - `initiated`, `in-progress` and `processing` keep the attempt open, and the client polls.
  - `done` with candidate speech stores the transcript and runs the existing evidence-verified analysis,
    which hands the screening to HR review (human gate 2).
  - Failed, abandoned and interrupted sessions get distinct outcomes.
  - A conditional update makes completion idempotent, so duplicate requests never produce a second
    result or status change.
"""

import logging
from datetime import datetime, timedelta, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from candidates.models import CandidateEvent, CandidateStatus
from candidates.services.status import record_event
from requisitions.models import RequisitionStatus
from .. import script
from ..models import (
    CallAttemptStatus, CallOutcome, NextStepRecommendation, Screening, ScreeningCallAttempt, ScreeningChannel,
    ScreeningStatus,
)
from .calls import ScreeningError, _escalate, automated_call_blocker, normalize_transcript, run_analysis
from .voice import BROWSER_PROVIDER_NAME, VoiceConfigurationError, VoiceNotFound, VoiceProviderError, get_browser_voice_client

logger = logging.getLogger(__name__)

EVENT = CandidateEvent.EventType
DESTINATION_LABEL = "Browser session"
PENDING_PROVIDER_STATES = {"initiated", "in-progress", "processing"}
TERMINAL_PROVIDER_STATES = {"done", "failed"}
CLIENT_END_REASONS = ("user_ended", "agent_ended", "connection_error", "start_failed", "page_closed", "unknown")
CLIENT_FAILURE_REASONS = {"connection_error", "start_failed"}
CLIENT_ID_MAX_CLOCK_SKEW = timedelta(minutes=5)


class SessionState:
    PROCESSING = "processing"  # ElevenLabs has not finished the conversation yet; ask again shortly
    CONCLUDED = "concluded"  # this request concluded the session
    ALREADY_CONCLUDED = "already_concluded"  # an earlier request (or the webhook/poller) concluded it


def _after_unsuccessful_session(screening, actor, outcome):
    """No usable answers: allow another session within the attempt limit, otherwise hand the case to HR."""
    screening.call_status = outcome
    if screening.attempt_count < screening.max_attempts:
        screening.status = ScreeningStatus.PENDING_CALL
        screening.next_attempt_not_before = None  # candidate-initiated: no calling-hours retry interval
        screening.save()
        return
    _escalate(
        screening, actor,
        f"No completed browser voice session after {screening.attempt_count} attempt(s) (last result: {outcome}). "
        "The attempt limit is reached; a recruiter must follow up, for example with a human-led screening.",
        NextStepRecommendation.HUMAN_FOLLOW_UP_REQUIRED,
    )


def start_browser_session(screening, actor, consent_acknowledged, client=None, now=None):
    """Claim the next attempt and mint a WebRTC conversation token. Returns attempt, token and dynamic variables."""
    now = now or timezone.now()
    client = client or get_browser_voice_client()
    candidate = screening.candidate
    if screening.channel != ScreeningChannel.BROWSER_VOICE:
        raise ScreeningError("This screening is not a browser voice screening.")
    if consent_acknowledged is not True:
        raise ScreeningError(
            "Confirm the disclosure first: AI voice agent, voice processed by ElevenLabs, transcript retained "
            "for HR review, and microphone access required."
        )
    if screening.status != ScreeningStatus.PENDING_CALL:
        raise ScreeningError("This screening is not waiting for a session. A session may already be active.")
    if candidate.current_status != CandidateStatus.SCREENING_SCHEDULED_PENDING:
        raise ScreeningError("The candidate is not at the screening-pending stage.")
    if screening.requisition.status != RequisitionStatus.OPEN:
        raise ScreeningError("Screening sessions are only allowed for open requisitions.")
    blocker = automated_call_blocker(candidate)
    if blocker:
        raise ScreeningError(blocker)
    if screening.attempt_count >= screening.max_attempts:
        raise ScreeningError("The maximum number of screening attempts has been reached.")
    if not client.is_configured:
        raise VoiceConfigurationError(
            "Browser voice screening is not configured on the server. Set ELEVENLABS_API_KEY and ELEVENLABS_AGENT_ID "
            "in backend/.env and restart the server, or use a human-led screening."
        )

    # Atomic claim: duplicate clicks or concurrent requests cannot open a second session for this screening.
    claimed = Screening.objects.filter(
        pk=screening.pk, status=ScreeningStatus.PENDING_CALL, attempt_count=screening.attempt_count,
    ).update(status=ScreeningStatus.CALL_IN_PROGRESS, attempt_count=F("attempt_count") + 1, updated_at=now)
    if not claimed:
        raise ScreeningError("A browser session is already being started for this screening.")
    screening.refresh_from_db()
    attempt = ScreeningCallAttempt.objects.create(
        screening=screening, attempt_number=screening.attempt_count, provider=BROWSER_PROVIDER_NAME,
        destination_masked=DESTINATION_LABEL, initiated_by=actor,
    )
    try:
        token = client.get_conversation_token()
    except (VoiceProviderError, VoiceConfigurationError) as exc:
        attempt.status = CallAttemptStatus.FAILED
        attempt.outcome = CallOutcome.FAILED
        attempt.error_code = "SESSION_TOKEN_FAILED"
        attempt.error_message = str(exc)[:500]
        attempt.ended_at = now
        attempt.save()
        with transaction.atomic():
            record_event(candidate, actor, EVENT.SCREENING_BROWSER_SESSION_FAILED, screening_id=str(screening.public_id),
                         attempt=attempt.attempt_number, error_code=attempt.error_code)
            _after_unsuccessful_session(screening, actor, CallOutcome.FAILED)
        raise
    attempt.status = CallAttemptStatus.IN_PROGRESS
    attempt.provider_conversation_id = token["conversation_id"]
    attempt.save()
    screening.call_timestamp = now
    screening.error_code = screening.error_message = ""
    screening.save(update_fields=("call_timestamp", "error_code", "error_message", "updated_at"))
    record_event(candidate, actor, EVENT.SCREENING_BROWSER_SESSION_STARTED, screening_id=str(screening.public_id),
                 attempt=attempt.attempt_number, channel=screening.channel, script_version=screening.script_version,
                 disclosure_acknowledged=True)
    variables = script.build_browser_dynamic_variables(
        screening, settings.SCREENING_ORGANIZATION_NAME, settings.SCREENING_HUMAN_CONTACT,
    )
    return {"attempt": attempt, "conversation_token": token["token"], "dynamic_variables": variables}


def _fetch_conversation(client, attempt, client_conversation_id):
    """Fetch the session's conversation by the stored ID.

    The browser-reported ID is used only if the stored one is missing or unknown to ElevenLabs. Even then
    it must belong to the configured agent, must have started after this attempt, and must not be linked
    to another attempt.
    """
    stored = attempt.provider_conversation_id
    candidates = [stored] if stored else []
    if client_conversation_id and client_conversation_id != stored:
        candidates.append(client_conversation_id)
    for conversation_id in candidates:
        from_client = conversation_id != stored
        if from_client and ScreeningCallAttempt.objects.filter(provider_conversation_id=conversation_id).exclude(pk=attempt.pk).exists():
            continue
        try:
            conversation = client.get_conversation(conversation_id)
        except VoiceNotFound:
            continue
        if from_client:
            if conversation.get("agent_id") != settings.ELEVENLABS_AGENT_ID:
                continue
            started = (conversation.get("metadata") or {}).get("start_time_unix_secs")
            if isinstance(started, (int, float)) and started < (attempt.started_at - CLIENT_ID_MAX_CLOCK_SKEW).timestamp():
                continue
            logger.warning("Browser session used the client-reported conversation id. attempt=%s", attempt.public_id)
        return conversation, conversation_id
    return None, None


def _session_start_time(conversation, fallback):
    started = (conversation.get("metadata") or {}).get("start_time_unix_secs") if conversation else None
    if isinstance(started, (int, float)) and started > 0:
        return datetime.fromtimestamp(started, tz=dt_timezone.utc)
    return fallback


def _termination_reason(conversation, client_end_reason):
    parts = []
    provider_reason = str(((conversation or {}).get("metadata") or {}).get("termination_reason") or "").strip()
    if provider_reason:
        parts.append(provider_reason)
    if client_end_reason and client_end_reason != "unknown":
        parts.append(f"browser reported: {client_end_reason}")
    return "; ".join(parts)[:255]


def conclude_browser_attempt(attempt, actor=None, client=None, provider=None, now=None,
                             client_end_reason="unknown", connected=None, client_conversation_id=None):
    """Conclude one browser session from the authoritative ElevenLabs conversation. Idempotent; returns a SessionState.

    `connected` and `client_end_reason` are hints from the browser. They only decide between "still waiting"
    and "abandoned/failed" when ElevenLabs has no usable conversation; they never supply answers.
    """
    now = now or timezone.now()
    timed_out = now - attempt.started_at >= timedelta(minutes=settings.SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES)
    screening = attempt.screening

    if attempt.status == CallAttemptStatus.INITIATING:
        # The token request is still in flight (or its worker died). Only a stale claim is released.
        if not timed_out:
            return SessionState.PROCESSING
        released = ScreeningCallAttempt.objects.filter(pk=attempt.pk, status=CallAttemptStatus.INITIATING).update(
            status=CallAttemptStatus.FAILED, outcome=CallOutcome.FAILED, error_code="SESSION_START_TIMEOUT",
            error_message="The session token request never completed.", ended_at=now, last_synced_at=now,
        )
        if not released:
            return SessionState.ALREADY_CONCLUDED
        with transaction.atomic():
            screening.refresh_from_db()
            record_event(screening.candidate, actor, EVENT.SCREENING_BROWSER_SESSION_FAILED, screening_id=str(screening.public_id),
                         attempt=attempt.attempt_number, error_code="SESSION_START_TIMEOUT")
            _after_unsuccessful_session(screening, actor, CallOutcome.FAILED)
        return SessionState.CONCLUDED
    if attempt.status != CallAttemptStatus.IN_PROGRESS:
        return SessionState.ALREADY_CONCLUDED

    client = client or get_browser_voice_client()
    conversation, conversation_id = _fetch_conversation(client, attempt, client_conversation_id)
    provider_status = (conversation.get("status") or "").lower() if conversation else ""
    never_connected = conversation is None or provider_status == "initiated"
    transcript = normalize_transcript(conversation) if conversation else []
    candidate_spoke = any(turn["role"] == "user" for turn in transcript)

    if never_connected:
        if connected is not False and not timed_out:
            outcome = None  # the browser may still be connecting, or ElevenLabs has not registered it yet
        else:
            outcome = CallOutcome.FAILED if client_end_reason in CLIENT_FAILURE_REASONS else CallOutcome.ABANDONED
    elif provider_status in PENDING_PROVIDER_STATES or (provider_status not in TERMINAL_PROVIDER_STATES and not timed_out):
        outcome = None  # transcript not final yet; do not assume it is available when the browser disconnects
    elif provider_status == "failed" or client_end_reason in CLIENT_FAILURE_REASONS:
        outcome = CallOutcome.INTERRUPTED if candidate_spoke else CallOutcome.FAILED
    else:
        outcome = CallOutcome.COMPLETED if candidate_spoke else CallOutcome.ABANDONED

    if outcome is None:
        ScreeningCallAttempt.objects.filter(pk=attempt.pk, status=CallAttemptStatus.IN_PROGRESS).update(
            provider_status=(provider_status or "not_found")[:32], last_synced_at=now,
        )
        return SessionState.PROCESSING

    metadata = (conversation or {}).get("metadata") or {}
    duration = metadata.get("call_duration_secs")
    with transaction.atomic():
        # Only one concurrent completion (browser, poller, webhook, manual check) may conclude the session.
        concluded = ScreeningCallAttempt.objects.filter(pk=attempt.pk, status=CallAttemptStatus.IN_PROGRESS).update(
            status=CallAttemptStatus.FAILED if never_connected and outcome == CallOutcome.FAILED else CallAttemptStatus.ENDED,
            outcome=outcome, ended_at=now, last_synced_at=now,
            provider_status=(provider_status or "not_found")[:32],
            provider_conversation_id=conversation_id or attempt.provider_conversation_id,
            termination_reason=_termination_reason(conversation, client_end_reason),
            duration_seconds=int(duration) if isinstance(duration, (int, float)) and duration >= 0 else None,
        )
        if not concluded:
            return SessionState.ALREADY_CONCLUDED
        attempt.refresh_from_db()
        screening.refresh_from_db()
        record_event(screening.candidate, actor, EVENT.SCREENING_BROWSER_SESSION_ENDED, screening_id=str(screening.public_id),
                     attempt=attempt.attempt_number, outcome=outcome, duration_seconds=attempt.duration_seconds,
                     client_end_reason=client_end_reason)
        if outcome in (CallOutcome.FAILED, CallOutcome.ABANDONED):
            _after_unsuccessful_session(screening, actor, outcome)
            return SessionState.CONCLUDED
        screening.transcript = transcript
        screening.status = ScreeningStatus.ANALYZING
        screening.call_timestamp = _session_start_time(conversation, attempt.started_at)
        screening.save(update_fields=("transcript", "status", "call_timestamp", "updated_at"))
    # Analysis runs outside the transaction (LLM call). On failure the transcript is kept for a retry.
    run_analysis(screening, actor=actor, provider=provider, client=client)
    return SessionState.CONCLUDED


def complete_browser_session(screening, actor, attempt_id=None, client=None, provider=None, now=None, **hints):
    """Browser-side "session ended" signal. Returns (attempt, SessionState)."""
    if screening.channel != ScreeningChannel.BROWSER_VOICE:
        raise ScreeningError("This screening is not a browser voice screening.")
    attempts = screening.call_attempts.all()
    if attempt_id:
        attempt = attempts.filter(public_id=attempt_id).first()
        if attempt is None:
            raise ScreeningError("This session does not belong to the screening.")
    else:
        attempt = attempts.filter(
            status__in=(CallAttemptStatus.IN_PROGRESS, CallAttemptStatus.INITIATING),
        ).order_by("-attempt_number").first() or attempts.order_by("-attempt_number").first()
        if attempt is None:
            raise ScreeningError("No browser session has been started for this screening.")
    state = conclude_browser_attempt(attempt, actor=actor, client=client, provider=provider, now=now, **hints)
    attempt.refresh_from_db()
    screening.refresh_from_db()
    return attempt, state
