"""Demo: emailed screening link (candidate-facing, token only). ElevenLabs and Azure are mocked."""

from unittest.mock import patch

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient, APITestCase

from candidates.models import CandidateEvent, CandidateStatus
from .models import ScreeningStatus
from .services.invite import invite_after_approval, make_token
from .test_browser_voice import BROWSER, FakeBrowserClient, CountingLLM, done
from .tests import ScreeningFixture


@override_settings(SCREENING_INVITE_EMAIL_ENABLED=True, EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   FRONTEND_BASE_URL="http://app.test", **BROWSER)
class ScreeningInviteTests(ScreeningFixture, APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.make_fixture()
        self.voice = FakeBrowserClient()
        for target, value in (("screening.services.browser.get_browser_voice_client", self.voice),
                              ("screening.services.calls.get_browser_voice_client", self.voice),
                              ("screening.services.analysis.get_llm_provider", CountingLLM())):
            patcher = patch(target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.public = APIClient()

    def invite(self):
        self.candidate.email = "cand@example.test"
        self.candidate.save()
        return invite_after_approval(self.candidate, self.recruiter)

    def test_approval_creates_screening_and_emails_link(self):
        screening = self.invite()
        self.assertEqual(screening.status, ScreeningStatus.PENDING_CALL)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["cand@example.test"])
        self.assertIn(f"http://app.test/screening-invite/{make_token(screening)}", mail.outbox[0].body)
        self.assertTrue(self.candidate.events.filter(event_type=CandidateEvent.EventType.SCREENING_INVITE_SENT).exists())

    def test_disabled_does_nothing(self):
        with override_settings(SCREENING_INVITE_EMAIL_ENABLED=False):
            self.assertIsNone(self.invite())
        self.assertEqual(len(mail.outbox), 0)

    def test_candidate_runs_session_without_login_and_sees_no_results(self):
        screening = self.invite()
        token = make_token(screening)
        info = self.public.get(reverse("screening:invite-info", args=[token]))
        self.assertEqual(info.status_code, 200)
        self.assertNotIn("questions", info.data)
        self.assertEqual(self.public.post(reverse("screening:invite-start", args=[token]),
                                          {"consent_acknowledged": False}, format="json").status_code, 400)
        started = self.public.post(reverse("screening:invite-start", args=[token]),
                                   {"consent_acknowledged": True}, format="json")
        self.assertEqual(started.status_code, 201, started.data)
        self.voice.conversations[started.data["conversation_id"]] = done()
        result = self.public.post(reverse("screening:invite-complete", args=[token]),
                                  {"attempt_id": started.data["attempt_id"], "client_end_reason": "user_ended", "connected": True},
                                  format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["status"], ScreeningStatus.AWAITING_HR_REVIEW)
        self.assertNotIn("transcript", result.data)
        self.candidate.refresh_from_db()

    def test_bad_token_is_404(self):
        self.assertEqual(self.public.get(reverse("screening:invite-info", args=["garbage"])).status_code, 404)
        self.assertEqual(self.public.post(reverse("screening:invite-start", args=["garbage"]),
                                          {"consent_acknowledged": True}, format="json").status_code, 404)
