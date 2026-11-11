"""Administrator reassigns an interview and removes a recruiter; candidate and both interviewers are emailed."""

from datetime import timedelta

from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import CandidateStatus
from communications.models import CommunicationLog, SendStatus
from .models import AvailabilitySlot, Interview, InterviewStatus
from .services.slots import local_window_to_utc
from .tests import Fixture


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend", FRONTEND_BASE_URL="https://hr.example.test")
class ReassignAndRemoveTests(Fixture, APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.make()  # self.recruiter is an ADMIN, self.manager has the RECRUITER role
        self.new = User.objects.create_user("new", "new@example.test", "Pass-12345!", role=UserRole.RECRUITER, first_name="Nia")
        self.start = (timezone.now() + timedelta(days=4)).replace(hour=10, minute=0, second=0, microsecond=0)
        self.interview = Interview.objects.create(
            candidate=self.candidate, requisition=self.requisition, interviewer=self.manager, timezone="UTC",
            mode="VIDEO", meeting_link="https://meet.example.test/x", duration_minutes=60,
            status=InterviewStatus.SCHEDULED, confirmed_start=self.start, confirmed_end=self.start + timedelta(hours=1),
            created_by=self.recruiter,
        )
        self.candidate.current_status = CandidateStatus.INTERVIEW_SCHEDULED
        self.candidate.save()
        self.client.force_authenticate(self.recruiter)
        self.url = reverse("scheduling:interview-reassign", args=[self.interview.public_id])
        self.new_day = (self.start + timedelta(days=1)).date()

    def test_reassign_emails_candidate_new_and_old_interviewer(self):
        r = self.client.post(self.url, {"interviewer": self.new.pk, "date": str(self.new_day), "start_time": "14:30", "timezone": "Asia/Karachi"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["emails"], {"candidate": "SENT", "new_interviewer": "SENT", "old_interviewer": "SENT"})
        recipients = sorted(sum((m.to for m in mail.outbox), []))
        self.assertEqual(recipients, ["hm@example.test", "new@example.test", "sara@example.test"])
        old_notice = next(m for m in mail.outbox if m.to == ["hm@example.test"])
        self.assertIn("reassigned", old_notice.subject.lower())
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.interviewer, self.new)
        self.assertEqual(self.interview.status, InterviewStatus.SCHEDULED)
        self.assertEqual(self.interview.sequence, 1)  # candidate receives an update of the earlier invitation
        self.assertEqual(CommunicationLog.objects.get().send_status, SendStatus.SENT)
        self.assertTrue(r.data["outside_declared_availability"])

    def test_double_booking_new_interviewer_is_refused(self):
        other = Candidate = self.candidate.__class__.objects.create(requisition=self.requisition, full_name="B", created_by=self.recruiter)
        Interview.objects.create(candidate=other, requisition=self.requisition, interviewer=self.new, timezone="UTC",
                                 status=InterviewStatus.SCHEDULED, confirmed_start=self.start + timedelta(days=1),
                                 confirmed_end=self.start + timedelta(days=1, hours=1), created_by=self.recruiter)
        local_start = (self.start + timedelta(days=1))
        r = self.client.post(self.url, {"interviewer": self.new.pk, "date": str(local_start.date()),
                                        "start_time": local_start.strftime("%H:%M"), "timezone": "UTC"}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.interviewer, self.manager)

    def test_time_only_change_notifies_candidate_and_same_interviewer(self):
        r = self.client.post(self.url, {"date": str(self.new_day), "start_time": "11:00", "timezone": "UTC"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["emails"], {"candidate": "SENT", "interviewer": "SENT"})
        self.assertEqual(sorted(sum((m.to for m in mail.outbox), [])), ["hm@example.test", "sara@example.test"])

    def test_nothing_to_change_and_past_time_and_non_admin_are_rejected(self):
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 400)
        past = (timezone.now() - timedelta(days=1)).date()
        self.assertEqual(self.client.post(self.url, {"date": str(past), "start_time": "10:00", "timezone": "UTC"}, format="json").status_code, 400)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(self.url, {"interviewer": self.new.pk}, format="json").status_code, 403)

    def test_candidate_without_email_still_reassigns_and_is_not_reported_sent(self):
        self.candidate.__class__.objects.filter(pk=self.candidate.pk).update(email=None)
        r = self.client.post(self.url, {"interviewer": self.new.pk}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["emails"]["candidate"], "NOT_SENT")
        self.assertEqual(r.data["emails"]["new_interviewer"], "SENT")

    def test_remove_recruiter_is_blocked_until_interviews_are_reassigned(self):
        remove = reverse("accounts:user-detail", args=[self.manager.pk])
        blocked = self.client.patch(remove, {"is_active": False}, format="json")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.data["pending_interviews"], 1)
        listed = self.client.get(reverse("scheduling:interviews"), {"interviewer": self.manager.pk, "upcoming": "1", "status": "ACTIVE"})
        self.assertEqual(len(listed.data), 1)
        self.client.post(self.url, {"interviewer": self.new.pk}, format="json")
        a_start, a_end = local_window_to_utc((timezone.now() + timedelta(days=9)).date(), __import__("datetime").time(9), __import__("datetime").time(12), "UTC")
        AvailabilitySlot.objects.create(interviewer=self.manager, start=a_start, end=a_end, timezone="UTC", created_by=self.manager)
        self.assertEqual(self.client.patch(remove, {"is_active": False}, format="json").status_code, 200)
        self.manager.refresh_from_db()
        self.assertFalse(self.manager.is_active)
        self.assertFalse(AvailabilitySlot.objects.filter(interviewer=self.manager).exists())
        self.assertEqual(self.client.patch(remove, {"is_active": True}, format="json").status_code, 200)  # can be reactivated
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_only_admins_remove_and_only_recruiters_can_be_removed(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(reverse("accounts:user-detail", args=[self.new.pk]), {"is_active": False}, format="json").status_code, 403)
        self.assertEqual(self.client.delete(reverse("accounts:user-detail", args=[self.new.pk])).status_code, 403)
        self.client.force_authenticate(self.recruiter)
        self.assertEqual(self.client.delete(reverse("accounts:user-detail", args=[self.recruiter.pk])).status_code, 400)
