"""Module 16: browser voice screening (ElevenLabs WebRTC). ElevenLabs is always mocked; nothing calls the network."""

import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import patch

import httpx
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from candidates.models import Candidate, CandidateEvent, CandidateStatus
from .models import CallAttemptStatus, CallOutcome, Screening, ScreeningCallAttempt, ScreeningStatus
from .services import calls
from .services.voice import ElevenLabsBrowserVoiceClient, VoiceNotFound
from .tests import TRANSCRIPT, FakeVoiceClient, ScreeningFixture, analysis_output

BROWSER = dict(
    SCREENING_VOICE_MODE="browser", ELEVENLABS_API_KEY="xi-test-key", ELEVENLABS_AGENT_ID="agent_test",
    ELEVENLABS_API_BASE_URL="https://api.elevenlabs.io", ELEVENLABS_AGENT_PHONE_NUMBER_ID="",
    TWILIO_ACCOUNT_SID="", TWILIO_AUTH_TOKEN="", TWILIO_PHONE_NUMBER="", ELEVENLABS_WEBHOOK_SECRET="",
    SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES=15,
)
START_UNIX = 1_793_000_000


def done(transcript=TRANSCRIPT, status="done", **metadata):
    return {"agent_id": "agent_test", "status": status, "transcript": transcript,
            "metadata": {"start_time_unix_secs": START_UNIX, "call_duration_secs": 95, **metadata}}


class FakeBrowserClient:
    """Stands in for ElevenLabsBrowserVoiceClient. `conversations` maps conversation id -> dict or exception."""

    is_configured = True

    def __init__(self, conversations=None, return_conversation_id=True, fail_token=None):
        self.conversations = conversations if conversations is not None else {}
        self.return_conversation_id = return_conversation_id
        self.fail_token = fail_token
        self.tokens = 0
        self.fetched = []
        self.deleted = []

    def get_conversation_token(self):
        if self.fail_token:
            raise self.fail_token
        self.tokens += 1
        return {"token": f"tok_{self.tokens}", "conversation_id": f"conv_b{self.tokens}" if self.return_conversation_id else None}

    def get_conversation(self, conversation_id):
        self.fetched.append(conversation_id)
        value = self.conversations.get(conversation_id)
        if value is None:
            raise VoiceNotFound("not found")
        if isinstance(value, Exception):
            raise value
        return value

    def delete_conversation(self, conversation_id):
        self.deleted.append(conversation_id)


class CountingLLM:
    deployment_name = "gpt-5-mini-test"

    def __init__(self, output=None):
        self.output = output or analysis_output()
        self.calls = 0

    def generate_structured(self, messages, response_model, **kwargs):
        self.calls += 1
        return self.output


class MockElevenLabs:
    """httpx transport that records every request and serves canned ElevenLabs responses."""

    def __init__(self, token_response=None, conversation=None):
        self.requests = []
        self.token_response = token_response or httpx.Response(200, json={"token": "webrtc-token", "conversation_id": "conv_live1"})
        self.conversation = conversation

    def __call__(self, request):
        self.requests.append(request)
        if request.url.path == "/v1/convai/conversation/token":
            return self.token_response
        if request.url.path.startswith("/v1/convai/conversations/"):
            if isinstance(self.conversation, Exception):
                raise self.conversation
            return self.conversation or httpx.Response(404, json={"detail": "not found"})
        return httpx.Response(500)

    def client(self):
        return ElevenLabsBrowserVoiceClient(http_client=httpx.Client(transport=httpx.MockTransport(self)))


@override_settings(**BROWSER)
class BrowserVoiceAPITests(ScreeningFixture, APITestCase):
    def setUp(self):
        # DRF throttle history lives in the process-wide cache and user pks repeat after each rollback; these
        # API-heavy tests must not exhaust the shared 120/min budget of tests that run after them.
        cache.clear()
        self.addCleanup(cache.clear)
        self.make_fixture()
        self.client.force_authenticate(self.recruiter)
        self.voice = FakeBrowserClient()
        self.llm = CountingLLM()
        for target, value in (("screening.services.browser.get_browser_voice_client", self.voice),
                              ("screening.services.calls.get_browser_voice_client", self.voice),
                              ("screening.services.analysis.get_llm_provider", self.llm)):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    # helpers -------------------------------------------------------------------------------------------
    def create(self, candidate=None, **body):
        candidate = candidate or self.candidate
        return self.client.post(reverse("screening:candidate-screenings", args=[candidate.public_id]), body, format="json")

    def start(self, screening_id, consent=True):
        return self.client.post(reverse("screening:browser-session-start", args=[screening_id]),
                                {"consent_acknowledged": consent}, format="json")

    def complete(self, screening_id, **body):
        return self.client.post(reverse("screening:browser-session-complete", args=[screening_id]), body, format="json")

    def started_session(self):
        screening_id = self.create(channel="BROWSER_VOICE").data["public_id"]
        response = self.start(screening_id)
        self.assertEqual(response.status_code, 201, response.data)
        return screening_id, response.data

    def events(self, event_type):
        return CandidateEvent.objects.filter(candidate=self.candidate, event_type=event_type)

    # creation / eligibility ------------------------------------------------------------------------------
    def test_default_ai_route_is_browser_and_phone_calls_are_disabled(self):
        response = self.create()
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["channel"], "BROWSER_VOICE")
        self.assertEqual(response.data["status"], "PENDING_CALL")
        self.assertEqual(response.data["script_version"], "screening-browser-v4")
        other = Candidate.objects.create(requisition=self.requisition, full_name="Sara Ahmed", phone="03001112222",
                                         current_status=CandidateStatus.APPROVED_FOR_SCREENING, created_by=self.recruiter)
        refused = self.create(candidate=other, channel="AI_VOICE", start_call_now=True)
        self.assertEqual(refused.status_code, 400)
        self.assertIn("disabled", str(refused.data))
        # A historical phone screening can no longer place a Twilio call in browser mode.
        legacy = Screening.objects.create(candidate=other, requisition=self.requisition, channel="AI_VOICE",
                                          status=ScreeningStatus.PENDING_CALL, questions=["Q?"], script_version="v",
                                          created_by=self.recruiter)
        phone = FakeVoiceClient()
        with self.assertRaisesMessage(calls.ScreeningError, "disabled"):
            calls.place_call(legacy, self.recruiter, client=phone)
        self.assertEqual(phone.started, [])

    def test_candidate_not_eligible(self):
        self.candidate.current_status = CandidateStatus.SCORED_HR_REVIEW
        self.candidate.save()
        self.assertEqual(self.create(channel="BROWSER_VOICE").status_code, 400)
        self.candidate.current_status = CandidateStatus.APPROVED_FOR_SCREENING
        self.candidate.consent_preferences = {"automated_call_opt_out": True}
        self.candidate.save()
        refused = self.create(channel="BROWSER_VOICE")
        self.assertEqual(refused.status_code, 400)
        self.assertIn("opted out", str(refused.data))
        # A human-led screening cannot be turned into a voice session.
        human = self.create(channel="HUMAN_LED").data["public_id"]
        self.assertEqual(self.start(human).status_code, 400)
        self.assertEqual(self.voice.tokens, 0)

    def test_consent_acknowledgement_is_required(self):
        screening_id = self.create(channel="BROWSER_VOICE").data["public_id"]
        response = self.start(screening_id, consent=False)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.voice.tokens, 0)
        self.assertFalse(ScreeningCallAttempt.objects.exists())

    def test_unauthorized_users_cannot_start_or_complete(self):
        screening_id = self.create(channel="BROWSER_VOICE").data["public_id"]
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.start(screening_id).status_code, 403)
        self.assertEqual(self.complete(screening_id).status_code, 403)
        self.client.force_authenticate(None)
        self.assertEqual(self.start(screening_id).status_code, 401)
        self.assertEqual(self.voice.tokens, 0)

    # start ----------------------------------------------------------------------------------------------
    def test_start_returns_token_and_minimum_data_only(self):
        screening_id, data = self.started_session()
        self.assertEqual(data["conversation_token"], "tok_1")
        self.assertEqual(data["conversation_id"], "conv_b1")
        self.assertEqual(data["connection_type"], "webrtc")
        self.assertEqual(data["dynamic_variables"]["candidate_name"], "Ali")  # first name only
        self.assertIn("1. Years of Django experience?", data["dynamic_variables"]["screening_questions"])
        serialized = json.dumps(data)
        for secret_or_pii in ("xi-test-key", "agent_test", "0300", "1234567", "ali@example.test", "Khan"):
            self.assertNotIn(secret_or_pii, serialized)
        attempt = ScreeningCallAttempt.objects.get()
        self.assertEqual((attempt.provider, attempt.destination_masked, attempt.status),
                         ("elevenlabs_webrtc", "Browser session", CallAttemptStatus.IN_PROGRESS))
        self.assertEqual(attempt.provider_conversation_id, "conv_b1")
        self.assertEqual(Screening.objects.get().status, ScreeningStatus.CALL_IN_PROGRESS)
        self.assertEqual(self.events("SCREENING_BROWSER_SESSION_STARTED").count(), 1)
        self.assertFalse(self.events("SCREENING_CALL_STARTED").exists())  # never presented as a phone call
        # A second start while the session is active is refused (no duplicate session).
        self.assertEqual(self.start(screening_id).status_code, 400)
        self.assertEqual(self.voice.tokens, 1)

    @override_settings(ELEVENLABS_API_KEY="")
    def test_missing_configuration_is_actionable_and_consumes_no_attempt(self):
        with patch("screening.services.browser.get_browser_voice_client", return_value=ElevenLabsBrowserVoiceClient()):
            screening_id = self.create(channel="BROWSER_VOICE").data["public_id"]
            response = self.start(screening_id)
        self.assertEqual(response.status_code, 503)
        self.assertIn("ELEVENLABS_API_KEY", str(response.data))
        screening = Screening.objects.get()
        self.assertEqual((screening.status, screening.attempt_count), (ScreeningStatus.PENDING_CALL, 0))

    def test_invalid_credentials_record_a_failed_attempt(self):
        mock = MockElevenLabs(token_response=httpx.Response(401, json={"detail": "invalid api key"}))
        with patch("screening.services.browser.get_browser_voice_client", return_value=mock.client()):
            screening_id = self.create(channel="BROWSER_VOICE").data["public_id"]
            response = self.start(screening_id)
        self.assertEqual(response.status_code, 502)
        self.assertIn("HTTP 401", str(response.data))
        self.assertNotIn("xi-test-key", str(response.data))
        attempt = ScreeningCallAttempt.objects.get()
        self.assertEqual((attempt.status, attempt.error_code), (CallAttemptStatus.FAILED, "SESSION_TOKEN_FAILED"))
        self.assertEqual(Screening.objects.get().status, ScreeningStatus.PENDING_CALL)
        self.assertEqual(self.events("SCREENING_BROWSER_SESSION_FAILED").count(), 1)

    def test_token_request_uses_server_side_key_and_agent(self):
        mock = MockElevenLabs()
        result = mock.client().get_conversation_token()
        self.assertEqual(result, {"token": "webrtc-token", "conversation_id": "conv_live1"})
        request = mock.requests[0]
        self.assertEqual((request.method, request.url.host, request.url.path),
                         ("GET", "api.elevenlabs.io", "/v1/convai/conversation/token"))
        self.assertEqual(request.url.params["agent_id"], "agent_test")
        self.assertEqual(request.headers["xi-api-key"], "xi-test-key")

    # completion -----------------------------------------------------------------------------------------
    def test_transcript_is_fetched_from_elevenlabs_and_enters_hr_review(self):
        screening_id, data = self.started_session()
        self.voice.conversations["conv_b1"] = done()
        response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True,
                                 transcript=[{"role": "user", "message": "forged answer"}])
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["session_state"], "concluded")
        self.assertEqual(response.data["status"], "AWAITING_HR_REVIEW")
        screening = Screening.objects.get()
        self.assertEqual(len(screening.transcript), len(TRANSCRIPT))
        self.assertNotIn("forged", json.dumps(screening.transcript))  # browser-posted text is ignored
        self.assertEqual(screening.call_timestamp.timestamp(), START_UNIX)
        attempt = ScreeningCallAttempt.objects.get()
        self.assertEqual((attempt.status, attempt.outcome, attempt.duration_seconds),
                         (CallAttemptStatus.ENDED, CallOutcome.COMPLETED, 95))
        self.assertIn("browser reported: user_ended", attempt.termination_reason)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        # The AI never progresses the candidate; HR must decide (human gate 2).
        review = self.client.post(reverse("screening:review", args=[screening_id]), {"decision": "APPROVE_FOR_INTERVIEW"}, format="json")
        self.assertEqual(review.status_code, 201, review.data)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.APPROVED_FOR_INTERVIEW)

    def test_processing_conversation_is_not_assumed_finished(self):
        screening_id, data = self.started_session()
        self.voice.conversations["conv_b1"] = done(status="processing", transcript=TRANSCRIPT[:2])
        response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data["session_state"], "processing")
        self.assertEqual(response.data["status"], "CALL_IN_PROGRESS")
        attempt = ScreeningCallAttempt.objects.get()
        self.assertEqual((attempt.status, attempt.provider_status), (CallAttemptStatus.IN_PROGRESS, "processing"))
        self.assertEqual(self.llm.calls, 0)
        self.voice.conversations["conv_b1"] = done()
        response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        self.assertEqual((response.status_code, response.data["session_state"]), (200, "concluded"))
        self.assertEqual(Screening.objects.get().status, ScreeningStatus.AWAITING_HR_REVIEW)

    def test_failed_conversation_allows_retry_then_escalates_to_hr(self):
        screening_id = self.create(channel="BROWSER_VOICE").data["public_id"]
        Screening.objects.filter(public_id=screening_id).update(max_attempts=2)
        for number in (1, 2):
            data = self.start(screening_id).data
            self.voice.conversations[f"conv_b{number}"] = done(status="failed", transcript=[])
            response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="agent_ended", connected=True)
            self.assertEqual(response.status_code, 200, response.data)
        attempts = list(ScreeningCallAttempt.objects.order_by("attempt_number"))
        self.assertEqual([a.outcome for a in attempts], [CallOutcome.FAILED, CallOutcome.FAILED])
        screening = Screening.objects.get()
        self.assertEqual(screening.status, ScreeningStatus.AWAITING_HR_REVIEW)
        self.assertEqual(screening.recommended_next_step_for_human_review, "HUMAN_FOLLOW_UP_REQUIRED")
        self.assertEqual(screening.call_status, CallOutcome.FAILED)
        self.assertEqual(self.llm.calls, 0)

    def test_duplicate_completion_requests_conclude_once(self):
        screening_id, data = self.started_session()
        self.voice.conversations["conv_b1"] = done()
        first = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        second = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        third = self.complete(screening_id)  # e.g. a retry without the attempt id
        self.assertEqual(first.data["session_state"], "concluded")
        self.assertEqual(second.data["session_state"], "already_concluded")
        self.assertEqual(third.data["session_state"], "already_concluded")
        self.assertEqual(self.llm.calls, 1)
        self.assertEqual(self.events("SCREENING_RESULT_RECORDED").count(), 1)
        self.assertEqual(self.events("SCREENING_BROWSER_SESSION_ENDED").count(), 1)
        to_review = [e for e in self.events("STATUS_CHANGED") if e.details.get("to") == CandidateStatus.SCREENING_COMPLETED_HR_REVIEW]
        self.assertEqual(len(to_review), 1)

    def test_never_connected_and_abandoned_sessions_are_distinguished(self):
        screening_id, data = self.started_session()
        response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="start_failed", connected=False)
        self.assertEqual(response.status_code, 200)
        attempt = ScreeningCallAttempt.objects.get(attempt_number=1)
        self.assertEqual((attempt.status, attempt.outcome), (CallAttemptStatus.FAILED, CallOutcome.FAILED))
        self.assertEqual(Screening.objects.get().status, ScreeningStatus.PENDING_CALL)

        data = self.start(screening_id).data
        response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=False)
        self.assertEqual(ScreeningCallAttempt.objects.get(attempt_number=2).outcome, CallOutcome.ABANDONED)

        data = self.start(screening_id).data  # connected, but the candidate never spoke
        self.voice.conversations["conv_b3"] = done(transcript=[{"role": "agent", "message": "Hello?"}])
        self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        self.assertEqual(ScreeningCallAttempt.objects.get(attempt_number=3).outcome, CallOutcome.ABANDONED)
        self.assertEqual(self.llm.calls, 0)

    def test_interrupted_session_is_never_reported_as_completed(self):
        screening_id, data = self.started_session()
        self.voice.conversations["conv_b1"] = done()
        self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="connection_error", connected=True)
        attempt = ScreeningCallAttempt.objects.get()
        self.assertEqual(attempt.outcome, CallOutcome.INTERRUPTED)
        screening = Screening.objects.get()
        self.assertEqual(screening.status, ScreeningStatus.AWAITING_HR_REVIEW)
        self.assertEqual(screening.call_status, CallOutcome.INTERRUPTED)
        self.assertTrue(any("interrupted" in w for w in screening.analysis_warnings))
        # HR sees the interrupted outcome and warning, then may still approve with one click (no reason needed).
        review_url = reverse("screening:review", args=[screening_id])
        self.assertEqual(self.client.post(review_url, {"decision": "APPROVE_FOR_INTERVIEW"}, format="json").status_code, 201)
        self.assertEqual(Screening.objects.get().call_status, CallOutcome.INTERRUPTED)  # outcome stays on record

    def test_provider_timeout_is_reported_and_safe_to_retry(self):
        screening_id, data = self.started_session()
        mock = MockElevenLabs(conversation=httpx.ReadTimeout("timed out"))
        with patch("screening.services.browser.get_browser_voice_client", return_value=mock.client()):
            response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
            self.assertEqual(response.status_code, 502)
            self.assertIn("Nothing was lost", str(response.data))
            self.assertEqual(ScreeningCallAttempt.objects.get().status, CallAttemptStatus.IN_PROGRESS)
            mock.conversation = httpx.Response(200, json=done())
            response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        self.assertEqual((response.status_code, response.data["session_state"]), (200, "concluded"))

    def test_abandoned_page_is_recovered_by_status_check_after_timeout(self):
        screening_id, _ = self.started_session()
        self.voice.conversations["conv_b1"] = {"agent_id": "agent_test", "status": "initiated", "transcript": [], "metadata": {}}
        sync_url = reverse("screening:sync", args=[screening_id])
        self.assertEqual(self.client.post(sync_url).data["status"], "CALL_IN_PROGRESS")
        ScreeningCallAttempt.objects.update(started_at=timezone.now() - timedelta(minutes=20))
        self.assertEqual(self.client.post(sync_url).data["status"], "PENDING_CALL")
        self.assertEqual(ScreeningCallAttempt.objects.get().outcome, CallOutcome.ABANDONED)

    def test_client_reported_conversation_id_is_verified_before_use(self):
        self.voice.return_conversation_id = False
        screening_id, data = self.started_session()
        self.assertIsNone(data["conversation_id"])
        self.voice.conversations["conv_other_agent"] = {**done(), "agent_id": "someone_else"}
        response = self.complete(screening_id, attempt_id=data["attempt_id"], conversation_id="conv_other_agent",
                                 client_end_reason="user_ended", connected=True)
        self.assertEqual(response.data["session_state"], "processing")  # foreign conversation rejected
        self.voice.conversations["conv_real"] = done(start_time_unix_secs=int(time.time()))
        response = self.complete(screening_id, attempt_id=data["attempt_id"], conversation_id="conv_real",
                                 client_end_reason="user_ended", connected=True)
        self.assertEqual(response.data["session_state"], "concluded")
        self.assertEqual(ScreeningCallAttempt.objects.get().provider_conversation_id, "conv_real")
        bad = self.complete(screening_id, conversation_id="../../v1/user")
        self.assertEqual(bad.status_code, 400)

    def test_rescreen_with_ai_creates_a_browser_session_in_browser_mode(self):
        screening_id, data = self.started_session()
        self.voice.conversations["conv_b1"] = done()
        self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        response = self.client.post(reverse("screening:review", args=[screening_id]),
                                    {"decision": "RESCREEN_AI_CALL", "decision_reason": "Answers unclear"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        follow_up = Screening.objects.get(public_id=response.data["review"]["follow_up_screening"])
        self.assertEqual(follow_up.channel, "BROWSER_VOICE")

    @override_settings(ELEVENLABS_WEBHOOK_SECRET="whsec")
    def test_webhook_concludes_browser_sessions_without_twilio(self):
        screening_id, _ = self.started_session()
        self.voice.conversations["conv_b1"] = done()
        body = json.dumps({"type": "post_call_transcription", "data": {"conversation_id": "conv_b1"}})
        ts = str(int(time.time()))
        sig = hmac.new(b"whsec", f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
        response = self.client.post(reverse("screening:elevenlabs-webhook"), body, content_type="application/json",
                                    HTTP_ELEVENLABS_SIGNATURE=f"t={ts},v0={sig}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Screening.objects.get().status, ScreeningStatus.AWAITING_HR_REVIEW)

    def test_full_flow_needs_no_twilio_and_no_phone_number(self):
        self.candidate.phone = ""
        self.candidate.save()
        mock = MockElevenLabs(conversation=httpx.Response(200, json=done()))
        with patch("screening.services.browser.get_browser_voice_client", return_value=mock.client()):
            screening_id, data = self.started_session()
            response = self.complete(screening_id, attempt_id=data["attempt_id"], client_end_reason="user_ended", connected=True)
        self.assertEqual(response.data["status"], "AWAITING_HR_REVIEW")
        self.assertEqual({r.url.host for r in mock.requests}, {"api.elevenlabs.io"})
        self.assertEqual([r.url.path for r in mock.requests],
                         ["/v1/convai/conversation/token", "/v1/convai/conversations/conv_live1"])
        config = self.client.get(reverse("screening:agent-config")).data
        self.assertEqual(config["voice_mode"], "browser")
        self.assertTrue(config["integration"]["browser_voice_ready"])
        self.assertFalse(config["integration"]["twilio_account_sid"])
