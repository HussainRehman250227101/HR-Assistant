"""Interviewers can subscribe to a private .ics feed of their interviews from Google/Outlook/Apple Calendar."""

from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from .models import Interview, InterviewStatus
from .tests import Fixture


@override_settings(PUBLIC_BACKEND_URL="https://api.example.test", FRONTEND_BASE_URL="https://hr.example.test")
class CalendarFeedTests(Fixture, APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.make()
        start = (timezone.now() + timedelta(days=2)).replace(microsecond=0)
        self.interview = Interview.objects.create(
            candidate=self.candidate, requisition=self.requisition, interviewer=self.manager, timezone="UTC",
            status=InterviewStatus.SCHEDULED, confirmed_start=start, confirmed_end=start + timedelta(hours=1),
            meeting_link="https://meet.example.test/x", created_by=self.recruiter)

    def subscribe(self, user, rotate=False):
        self.client.force_authenticate(user)
        method = self.client.post if rotate else self.client.get
        url = method(reverse("scheduling:calendar-subscription")).data["url"]
        self.client.force_authenticate(None)
        return url

    def test_feed_lists_only_the_owners_interviews_without_contact_details(self):
        url = self.subscribe(self.manager)
        self.assertTrue(url.startswith("https://api.example.test/api/v1/scheduling/calendar/"))
        path = url.replace("https://api.example.test", "")
        response = self.client.get(path)  # no authentication: the secret is in the URL
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/calendar; charset=utf-8")
        text = response.content.decode().replace("\r\n ", "")  # unfold long lines
        self.assertIn("BEGIN:VEVENT", text)
        self.assertIn("Interview: Sara Ahmed - Backend Engineer", text)
        self.assertIn(f"/candidates/{self.candidate.public_id}", text)
        self.assertNotIn("sara@example.test", text)
        self.assertNotIn("03001234567", text)
        other = User.objects.create_user("o", "o@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        other_text = self.client.get(self.subscribe(other).replace("https://api.example.test", "")).content.decode()
        self.assertNotIn("BEGIN:VEVENT", other_text)

    def test_cancelled_interviews_leave_the_feed_and_lines_are_folded(self):
        path = self.subscribe(self.manager).replace("https://api.example.test", "")
        Interview.objects.filter(pk=self.interview.pk).update(status=InterviewStatus.CANCELLED)
        self.assertNotIn("BEGIN:VEVENT", self.client.get(path).content.decode())
        Interview.objects.filter(pk=self.interview.pk).update(status=InterviewStatus.SCHEDULED, location="x" * 200, meeting_link="")
        lines = self.client.get(path).content.decode().split("\r\n")
        self.assertTrue(all(len(line.encode()) <= 75 for line in lines))

    def test_regenerating_revokes_the_old_url_and_wrong_tokens_404(self):
        old = self.subscribe(self.manager).replace("https://api.example.test", "")
        new = self.subscribe(self.manager, rotate=True).replace("https://api.example.test", "")
        self.assertNotEqual(old, new)
        self.assertEqual(self.client.get(old).status_code, 404)
        self.assertEqual(self.client.get(new).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/scheduling/calendar/not-a-token/interviews.ics").status_code, 404)

    def test_subscription_endpoint_requires_sign_in_and_deactivated_users_lose_the_feed(self):
        self.assertEqual(self.client.get(reverse("scheduling:calendar-subscription")).status_code, 401)
        path = self.subscribe(self.manager).replace("https://api.example.test", "")
        User.objects.filter(pk=self.manager.pk).update(is_active=False)
        self.assertEqual(self.client.get(path).status_code, 404)
