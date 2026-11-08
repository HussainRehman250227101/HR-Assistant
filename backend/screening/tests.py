import hashlib
import hmac
import json
import time
from datetime import datetime, timezone as dt_timezone

from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateEvent, CandidateStatus, ConsentStatus
from requisitions.models import Requisition, RequisitionStatus
from .models import CallAttemptStatus, CallOutcome, ScreeningStatus
from .schemas import QuestionAnswer, RoleRequirementResponse, SalaryExpectation, ScreeningAnalysisOutput, StatedAnswer
from .services import calls
from .services.phone import DestinationNotAllowed, mask_phone, validate_destination
from .services.voice import VoiceProviderError, verify_elevenlabs_signature

# Module 10 phone-call tests run in the optional telephony mode (browser mode is the default since Module 16).
ALWAYS_OPEN = dict(SCREENING_CALL_WINDOW_START_HOUR=0, SCREENING_CALL_WINDOW_END_HOUR=24, SCREENING_VOICE_MODE="telephony")


class FakeVoiceClient:
    is_configured = True

    def __init__(self, conversation=None, twilio=None, fail_start=False):
        self.started = []
        self.deleted = []
        self.conversation = conversation or {}
        self.twilio = twilio
        self.fail_start = fail_start

    def start_outbound_call(self, to_number, dynamic_variables):
        if self.fail_start:
            raise VoiceProviderError("boom")
        self.started.append((to_number, dynamic_variables))
        return {"conversation_id": f"conv_{len(self.started)}", "call_sid": f"CA{len(self.started)}"}

    def get_conversation(self, conversation_id):
        return self.conversation

    def get_twilio_call(self, call_sid):
        return self.twilio

    def delete_conversation(self, conversation_id):
        self.deleted.append(conversation_id)


class FakeLLM:
    deployment_name = "gpt-5-mini-test"

    def __init__(self, output):
        self.output = output

    def generate_structured(self, messages, response_model, **kwargs):
        return self.output


def analysis_output(**overrides):
    data = dict(
        call_outcome="COMPLETED", consent_status="GRANTED", ai_disclosure_given=True,
        question_answers=[
            QuestionAnswer(question_number=1, answer_status="ANSWERED",
                           candidate_statement="I have five years of Django experience",
                           agent_interpretation="Meets experience expectation"),
            QuestionAnswer(question_number=2, answer_status="ANSWERED",
                           candidate_statement="I invented the internet in 1950",
                           agent_interpretation="fabricated"),
        ],
        salary_expectation=SalaryExpectation(status="NOT_ASKED", minimum=None, maximum=None, currency="",
                                             period="UNSPECIFIED", candidate_statement=""),
        notice_period=StatedAnswer(status="STATED", summary="One month", candidate_statement="In one month."),
        interview_availability=StatedAnswer(status="NOT_ASKED", summary="", candidate_statement=""),
        role_requirement_responses=[RoleRequirementResponse(requirement="Python", candidate_statement="", status="UNCLEAR")],
        candidate_questions=["Is the role remote?"], unresolved_questions=[],
        concise_summary="Candidate answered both questions.",
        recommended_next_step_for_human_review="REVIEW_FOR_INTERVIEW_DECISION", warnings=[],
    )
    data.update(overrides)
    return ScreeningAnalysisOutput(**data)


TRANSCRIPT = [
    {"role": "agent", "message": "Hello, I am an AI assistant. Do you consent to recording?"},
    {"role": "user", "message": "Yes I consent."},
    {"role": "agent", "message": "How many years of Django experience do you have?"},
    {"role": "user", "message": "I have five years of Django experience, call me at 0300 1234567."},
    {"role": "agent", "message": "When can you start?"},
    {"role": "user", "message": "In one month."},
]


class ScreeningFixture:
    def make_fixture(self):
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department="Eng", description="Build APIs", status=RequisitionStatus.OPEN,
            screening_questions=["Years of Django experience?", "Notice period?"], required_skills=["Python"],
            created_by=self.recruiter, hiring_manager=self.manager,
        )
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Ali Khan", email="ali@example.test", phone="0300 1234567",
            current_status=CandidateStatus.APPROVED_FOR_SCREENING, created_by=self.recruiter,
        )


class PhoneTests(TestCase):
    def test_pakistani_formats_normalize_and_others_are_rejected(self):
        self.assertEqual(validate_destination("0300-1234567"), "+923001234567")
        self.assertEqual(validate_destination("00923001234567"), "+923001234567")
        with self.assertRaises(DestinationNotAllowed):
            validate_destination("+14155550100")
        with self.assertRaises(DestinationNotAllowed):
            validate_destination("+92300123")
        self.assertEqual(mask_phone("+923001234567"), "+92******4567")

    def test_webhook_signature(self):
        body = b'{"type":"post_call_transcription"}'
        ts = str(int(time.time()))
        sig = hmac.new(b"secret", f"{ts}.".encode() + body, hashlib.sha256).hexdigest()
        self.assertTrue(verify_elevenlabs_signature(body, f"t={ts},v0={sig}", "secret"))
        self.assertFalse(verify_elevenlabs_signature(body, f"t={ts},v0={sig}", "other"))
        self.assertFalse(verify_elevenlabs_signature(body, f"t=1,v0={sig}", "secret"))


@override_settings(**ALWAYS_OPEN)
class ScreeningServiceTests(ScreeningFixture, TestCase):
    def setUp(self):
        self.make_fixture()

    def test_create_requires_approved_status(self):
        self.candidate.current_status = CandidateStatus.SCORED_HR_REVIEW
        self.candidate.save()
        with self.assertRaises(calls.ScreeningError):
            calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")

    def test_create_rejects_non_pakistani_number_and_opt_out(self):
        self.candidate.phone = "+14155550100"
        self.candidate.save()
        with self.assertRaisesMessage(calls.ScreeningError, "+92"):
            calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        self.candidate.phone = "03001234567"
        self.candidate.consent_preferences = {"automated_call_opt_out": True}
        self.candidate.save()
        with self.assertRaisesMessage(calls.ScreeningError, "opted out"):
            calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        # The human-led alternative remains available.
        screening = calls.create_screening(self.candidate, self.recruiter, "HUMAN_LED")
        self.assertEqual(screening.status, ScreeningStatus.AWAITING_MANUAL_RESULT)

    def test_full_call_flow_with_verified_summary(self):
        screening = calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCREENING_SCHEDULED_PENDING)
        client = FakeVoiceClient(conversation={"status": "done", "transcript": TRANSCRIPT,
                                               "metadata": {"call_duration_secs": 95}}, twilio={"status": "completed"})
        attempt = calls.place_call(screening, self.recruiter, client=client)
        self.assertEqual(client.started[0][0], "+923001234567")
        self.assertIn("1. Years of Django experience?", client.started[0][1]["screening_questions"])
        self.assertEqual(attempt.status, CallAttemptStatus.IN_PROGRESS)
        # A second click cannot place a concurrent call.
        with self.assertRaises(calls.ScreeningError):
            calls.place_call(screening, self.recruiter, client=client)

        calls.sync_attempt(attempt, client=client, provider=FakeLLM(analysis_output()))
        screening.refresh_from_db()
        self.candidate.refresh_from_db()
        self.assertEqual(screening.status, ScreeningStatus.AWAITING_HR_REVIEW)
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        self.assertEqual(self.candidate.recording_consent_status, ConsentStatus.GRANTED)
        pairs = screening.question_answer_pairs
        self.assertEqual(pairs[0]["answer_status"], "ANSWERED")
        self.assertEqual(pairs[1]["answer_status"], "UNCLEAR")  # fabricated quote removed
        self.assertEqual(pairs[1]["candidate_statement"], "")
        self.assertIn("Notice period?", screening.unresolved_questions)
        self.assertTrue(any("could not be verified" in w for w in screening.analysis_warnings))
        # Contact details in the transcript were redacted before analysis; transcript retained for HR.
        self.assertEqual(len(screening.transcript), 6)
        # Re-sync is a no-op.
        calls.sync_attempt(attempt, client=client, provider=FakeLLM(analysis_output()))
        self.assertEqual(CandidateEvent.objects.filter(candidate=self.candidate, event_type="SCREENING_RESULT_RECORDED").count(), 1)

    def test_no_answer_respects_retry_limit_and_interval(self):
        screening = calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        screening.max_attempts = 2
        screening.save()
        client = FakeVoiceClient(conversation={"status": "failed", "transcript": []}, twilio={"status": "no-answer"})
        attempt = calls.place_call(screening, self.recruiter, client=client)
        calls.sync_attempt(attempt, client=client)
        screening.refresh_from_db()
        self.assertEqual(screening.status, ScreeningStatus.PENDING_CALL)
        self.assertEqual(screening.call_status, CallOutcome.NO_ANSWER)
        with self.assertRaisesMessage(calls.ScreeningError, "retry interval"):
            calls.place_call(screening, self.recruiter, client=client)
        screening.next_attempt_not_before = None
        screening.save()
        attempt = calls.place_call(screening, self.recruiter, client=client)
        calls.sync_attempt(attempt, client=client)
        screening.refresh_from_db()
        self.candidate.refresh_from_db()
        self.assertEqual(screening.status, ScreeningStatus.AWAITING_HR_REVIEW)
        self.assertEqual(screening.recommended_next_step_for_human_review, "HUMAN_FOLLOW_UP_REQUIRED")
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        self.assertEqual(len(client.started), 2)

    def test_consent_declined_discards_transcript_and_opts_out(self):
        screening = calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        client = FakeVoiceClient(conversation={"status": "done", "transcript": TRANSCRIPT[:2]})
        attempt = calls.place_call(screening, self.recruiter, client=client)
        output = analysis_output(call_outcome="CONSENT_DECLINED", consent_status="DECLINED", question_answers=[],
                                 recommended_next_step_for_human_review="OFFER_ALTERNATIVE_SCREENING")
        calls.sync_attempt(attempt, client=client, provider=FakeLLM(output))
        screening.refresh_from_db()
        self.candidate.refresh_from_db()
        self.assertEqual(screening.transcript, [])
        self.assertEqual(client.deleted, ["conv_1"])
        self.assertTrue(self.candidate.consent_preferences["automated_call_opt_out"])
        self.assertEqual(self.candidate.recording_consent_status, ConsentStatus.DECLINED)

    def test_provider_failure_is_recorded_and_counted(self):
        screening = calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        with self.assertRaises(VoiceProviderError):
            calls.place_call(screening, self.recruiter, client=FakeVoiceClient(fail_start=True))
        screening.refresh_from_db()
        self.assertEqual(screening.attempt_count, 1)
        self.assertEqual(screening.status, ScreeningStatus.PENDING_CALL)
        self.assertEqual(screening.call_attempts.get().status, CallAttemptStatus.FAILED)

    @override_settings(SCREENING_CALL_WINDOW_START_HOUR=9, SCREENING_CALL_WINDOW_END_HOUR=19)
    def test_calling_window_enforced(self):
        screening = calls.create_screening(self.candidate, self.recruiter, "AI_VOICE")
        night = datetime(2026, 11, 7, 20, 0, tzinfo=dt_timezone.utc)  # 01:00 in Asia/Karachi
        with self.assertRaisesMessage(calls.ScreeningError, "Calls are only allowed"):
            calls.place_call(screening, self.recruiter, client=FakeVoiceClient(), now=night)


@override_settings(**ALWAYS_OPEN)
class ScreeningAPITests(ScreeningFixture, APITestCase):
    def setUp(self):
        self.make_fixture()

    def test_human_led_flow_and_permissions(self):
        url = reverse("screening:candidate-screenings", args=[self.candidate.public_id])
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(url, {"channel": "HUMAN_LED"}, format="json").status_code, 403)
        self.client.force_authenticate(self.recruiter)
        response = self.client.post(url, {"channel": "HUMAN_LED"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        screening_id = response.data["public_id"]
        result = self.client.post(reverse("screening:manual-result", args=[screening_id]), {
            "call_status": "COMPLETED", "consent_status": "GRANTED",
            "question_answer_pairs": [{"question_number": 1, "answer_status": "ANSWERED", "candidate_statement": "4 years"}],
            "candidate_stated_availability": "Mornings", "concise_summary": "Good conversation.",
        }, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["status"], "AWAITING_HR_REVIEW")
        self.assertEqual(result.data["question_answer_pairs"][1]["answer_status"], "NOT_ASKED")
        # an interviewer-only recruiter sees an assigned candidate's summary but never the raw transcript
        from datetime import timedelta
        from django.utils import timezone
        from scheduling.models import Interview
        start = timezone.now() + timedelta(days=2)
        Interview.objects.create(candidate=self.candidate, requisition=self.candidate.requisition, interviewer=self.manager,
                                 timezone="UTC", status="SCHEDULED", confirmed_start=start, confirmed_end=start + timedelta(minutes=45),
                                 mode="ONSITE", location="Office", created_by=self.recruiter)
        self.client.force_authenticate(self.manager)
        detail = self.client.get(reverse("screening:detail", args=[screening_id]))
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.data["transcript"], [])

    @override_settings(ELEVENLABS_API_KEY="", ELEVENLABS_AGENT_ID="", ELEVENLABS_AGENT_PHONE_NUMBER_ID="")
    def test_unconfigured_provider_returns_actionable_error(self):
        self.client.force_authenticate(self.recruiter)
        response = self.client.post(reverse("screening:candidate-screenings", args=[self.candidate.public_id]),
                                    {"channel": "AI_VOICE", "start_call_now": True}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertIn("not configured", response.data["call_error"])
        self.assertEqual(response.data["attempt_count"], 0)

    @override_settings(ELEVENLABS_WEBHOOK_SECRET="whsec")
    def test_webhook_rejects_bad_signature(self):
        body = json.dumps({"type": "post_call_transcription", "data": {"conversation_id": "x"}})
        response = self.client.post(reverse("screening:elevenlabs-webhook"), body, content_type="application/json",
                                    HTTP_ELEVENLABS_SIGNATURE="t=1,v0=bad")
        self.assertEqual(response.status_code, 401)
        ts = str(int(time.time()))
        sig = hmac.new(b"whsec", f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()
        response = self.client.post(reverse("screening:elevenlabs-webhook"), body, content_type="application/json",
                                    HTTP_ELEVENLABS_SIGNATURE=f"t={ts},v0={sig}")
        self.assertEqual(response.status_code, 200)


@override_settings(**ALWAYS_OPEN)
class ScreeningReviewTests(ScreeningFixture, APITestCase):
    def setUp(self):
        self.make_fixture()
        self.client.force_authenticate(self.recruiter)

    def _completed_screening(self):
        screening = calls.create_screening(self.candidate, self.recruiter, "HUMAN_LED")
        return calls.record_manual_result(screening, self.recruiter, {
            "call_status": "COMPLETED", "consent_status": "GRANTED", "concise_summary": "ok",
            "question_answer_pairs": [{"question_number": 1, "answer_status": "ANSWERED", "candidate_statement": "5 years"}],
        })

    def test_approve_moves_candidate_to_interview_stage_once(self):
        screening = self._completed_screening()
        url = reverse("screening:review", args=[screening.public_id])
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(url, {"decision": "APPROVE_FOR_INTERVIEW"}, format="json").status_code, 403)
        self.client.force_authenticate(self.recruiter)
        response = self.client.post(url, {"decision": "APPROVE_FOR_INTERVIEW"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "REVIEWED")
        self.assertEqual(response.data["review"]["decision"], "APPROVE_FOR_INTERVIEW")
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.APPROVED_FOR_INTERVIEW)
        self.assertEqual(self.client.post(url, {"decision": "DECLINE", "decision_reason": "x"}, format="json").status_code, 400)

    def test_decline_requires_reason_and_closes(self):
        screening = self._completed_screening()
        url = reverse("screening:review", args=[screening.public_id])
        self.assertEqual(self.client.post(url, {"decision": "DECLINE"}, format="json").status_code, 400)
        self.assertEqual(self.client.post(url, {"decision": "DECLINE", "decision_reason": "Notice period too long"}, format="json").status_code, 201)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.CLOSED)
        self.assertEqual(self.candidate.closed_reason, "Notice period too long")

    def test_rescreen_creates_follow_up_screening(self):
        screening = self._completed_screening()
        response = self.client.post(reverse("screening:review", args=[screening.public_id]),
                                    {"decision": "RESCREEN_HUMAN_LED", "decision_reason": "Answers unclear"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertIsNotNone(response.data["review"]["follow_up_screening"])
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCREENING_SCHEDULED_PENDING)

    def test_rescreen_ai_blocked_after_opt_out(self):
        screening = self._completed_screening()
        self.candidate.consent_preferences = {"automated_call_opt_out": True}
        self.candidate.save()
        response = self.client.post(reverse("screening:review", args=[screening.public_id]),
                                    {"decision": "RESCREEN_AI_CALL", "decision_reason": "retry"}, format="json")
        self.assertEqual(response.status_code, 400)
        screening.refresh_from_db()
        self.assertEqual(screening.status, ScreeningStatus.AWAITING_HR_REVIEW)
