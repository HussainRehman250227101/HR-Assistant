"""The interviewer is emailed once each time a candidate is assigned to them."""

from datetime import timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import CandidateEvent
from .models import Interview
from .tests import Fixture


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_BASE_URL="https://hr.example.test")
class InterviewerNotificationTests(Fixture, APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.make()
        self.client.force_authenticate(self.recruiter)

    def plan(self, interviewer):
        return self.client.post(reverse("scheduling:candidate-interviews", args=[self.candidate.public_id]), {
            "interviewer": interviewer.pk, "duration_minutes": 60, "timezone": "Asia/Karachi", "mode": "VIDEO",
            "meeting_link": "https://meet.example.test/abc",
            "candidate_windows": [{"date": str(self.day), "start_time": "10:00", "end_time": "12:00"}],
        }, format="json")

    def events(self, kind):
        return self.candidate.events.filter(event_type=kind)

    def test_assignment_sends_one_email_with_link_and_no_contact_details(self):
        with self.captureOnCommitCallbacks(execute=True):
            self.assertEqual(self.plan(self.manager).status_code, 201)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["hm@example.test"])
        self.assertIn("Sara Ahmed", message.subject)
        self.assertIn(f"https://hr.example.test/candidates/{self.candidate.public_id}", message.body)
        self.assertNotIn("sara@example.test", message.body)
        self.assertNotIn("03001234567", message.body)
        self.assertEqual(self.events(CandidateEvent.EventType.INTERVIEWER_NOTIFIED).count(), 1)

    def test_same_interviewer_is_never_emailed_twice_but_a_new_one_is(self):
        with self.captureOnCommitCallbacks(execute=True):
            interview_id = self.plan(self.manager).data["public_id"]
        other = User.objects.create_user("other", "other@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        url = reverse("scheduling:interview-propose", args=[interview_id])
        body = {"candidate_windows": [{"date": str(self.day), "start_time": "10:00", "end_time": "12:00"}]}
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, body, format="json")  # same interviewer: no new email
        self.assertEqual(len(mail.outbox), 1)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(url, {**body, "interviewer": other.pk}, format="json")
        self.assertEqual([m.to for m in mail.outbox], [["hm@example.test"], ["other@example.test"]])

    def test_send_failure_is_recorded_and_does_not_break_scheduling(self):
        with mock.patch("scheduling.services.notifications.EmailMessage.send", side_effect=OSError("smtp down")):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.plan(self.manager)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.events(CandidateEvent.EventType.INTERVIEWER_NOTIFIED).count(), 0)
        self.assertEqual(self.events(CandidateEvent.EventType.INTERVIEWER_NOTIFICATION_FAILED).count(), 1)
        self.assertTrue(Interview.objects.filter(candidate=self.candidate).exists())

    def test_interviewer_without_email_is_recorded_not_claimed_sent(self):
        User.objects.filter(pk=self.manager.pk).update(email="")
        self.manager.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            self.plan(self.manager)
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(self.events(CandidateEvent.EventType.INTERVIEWER_NOTIFICATION_FAILED).count(), 1)
