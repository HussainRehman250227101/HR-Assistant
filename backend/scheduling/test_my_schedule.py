"""The personal schedule page (/my-schedule) relies on these rules: everyone who interviews manages their own
availability and sees only the interviews assigned to them; admins can still manage anyone's availability."""

from datetime import timedelta

from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateStatus
from requisitions.models import Requisition, RequisitionStatus
from .models import AvailabilitySlot, Interview, InterviewStatus


class MyScheduleAPITests(APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.admin = User.objects.create_user("adm", "adm@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.RECRUITER, first_name="Rida")
        self.other_recruiter = User.objects.create_user("rec2", "rec2@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department="Eng", description="APIs", status=RequisitionStatus.OPEN, created_by=self.admin,
        )
        self.day = (timezone.now() + timedelta(days=4)).date()

    def add_slot(self, user, payload_user=None, **extra):
        payload = {"date": str(self.day), "start_time": "10:00", "end_time": "12:00", "timezone": "Asia/Karachi", **extra}
        return self.client.post(reverse("scheduling:availability"), payload, format="json")

    def interview_for(self, interviewer, name, hours=0):
        candidate = Candidate.objects.create(
            requisition=self.requisition, full_name=name, created_by=self.admin, current_status=CandidateStatus.INTERVIEW_SCHEDULED,
        )
        start = timezone.now() + timedelta(days=4, hours=hours)
        return Interview.objects.create(
            candidate=candidate, requisition=self.requisition, interviewer=interviewer, timezone="Asia/Karachi",
            status=InterviewStatus.SCHEDULED, confirmed_start=start, confirmed_end=start + timedelta(minutes=45),
            mode="ONSITE", location="Netsol Lahore", created_by=self.admin,
        )

    def test_recruiter_adds_their_own_availability_without_naming_an_interviewer(self):
        self.client.force_authenticate(self.recruiter)
        response = self.add_slot(self.recruiter)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(AvailabilitySlot.objects.get().interviewer, self.recruiter)

    def test_availability_list_can_be_limited_to_one_person(self):
        self.client.force_authenticate(self.recruiter)
        self.add_slot(self.recruiter)
        self.client.force_authenticate(self.other_recruiter)
        self.add_slot(self.other_recruiter, start_time="14:00", end_time="15:00")
        self.client.force_authenticate(self.recruiter)
        mine = self.client.get(reverse("scheduling:availability"), {"interviewer": self.recruiter.pk}).data
        self.assertEqual([s["interviewer"] for s in mine], [self.recruiter.pk])

    def test_recruiter_only_ever_sees_interviews_assigned_to_them(self):
        mine = self.interview_for(self.recruiter, "Assigned To Rida")
        self.interview_for(self.other_recruiter, "Assigned Elsewhere", hours=3)
        self.client.force_authenticate(self.recruiter)
        everything = self.client.get(reverse("scheduling:interviews")).data
        assigned = self.client.get(reverse("scheduling:interviews"), {"mine": "1"}).data
        self.assertEqual([i["public_id"] for i in everything], [str(mine.public_id)])
        self.assertEqual(assigned, everything)
        detail = assigned[0]
        self.assertEqual((detail["candidate_name"], detail["requisition_title"], detail["mode"], detail["location"]),
                         ("Assigned To Rida", "Backend Engineer", "ONSITE", "Netsol Lahore"))
        self.assertEqual(detail["interviewer"], self.recruiter.pk)
        other = Interview.objects.get(interviewer=self.other_recruiter)
        self.assertEqual(self.client.get(reverse("scheduling:interview-detail", args=[other.public_id])).status_code, 404)
        # an admin sees both, and `mine` narrows an admin to their own
        self.client.force_authenticate(self.admin)
        self.assertEqual(len(self.client.get(reverse("scheduling:interviews")).data), 2)
        self.assertEqual(self.client.get(reverse("scheduling:interviews"), {"mine": "1"}).data, [])

    def test_status_filter_combines_with_mine(self):
        self.interview_for(self.recruiter, "Scheduled One")
        cancelled = self.interview_for(self.recruiter, "Cancelled One", hours=2)
        Interview.objects.filter(pk=cancelled.pk).update(status=InterviewStatus.CANCELLED, cancellation_reason="Withdrew")
        self.client.force_authenticate(self.recruiter)
        active = self.client.get(reverse("scheduling:interviews"), {"mine": "1", "status": "ACTIVE"}).data
        gone = self.client.get(reverse("scheduling:interviews"), {"mine": "1", "status": "CANCELLED"}).data
        self.assertEqual([i["candidate_name"] for i in active], ["Scheduled One"])
        self.assertEqual([(i["candidate_name"], i["cancellation_reason"]) for i in gone], [("Cancelled One", "Withdrew")])

    def test_admin_can_still_add_availability_for_a_recruiter_and_find_recruiters_in_the_directory(self):
        self.client.force_authenticate(self.admin)
        response = self.add_slot(self.admin, interviewer=self.recruiter.pk)
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(AvailabilitySlot.objects.get().interviewer, self.recruiter)
        directory = self.client.get(reverse("accounts:users")).data
        self.assertIn(self.recruiter.pk, {u["id"] for u in directory})
        self.assertEqual({u["role"] for u in directory if u["id"] == self.recruiter.pk}, {"RECRUITER"})

    def test_a_recruiter_cannot_manage_anyone_elses_availability(self):
        self.client.force_authenticate(self.other_recruiter)
        self.add_slot(self.other_recruiter)
        theirs = AvailabilitySlot.objects.get()
        self.client.force_authenticate(self.recruiter)
        refused = self.add_slot(self.recruiter, interviewer=self.other_recruiter.pk)
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(self.client.get(reverse("scheduling:availability"), {"interviewer": self.other_recruiter.pk}).data, [])
        self.assertEqual(self.client.delete(reverse("scheduling:availability-detail", args=[theirs.public_id])).status_code, 403)
        self.assertTrue(AvailabilitySlot.objects.filter(pk=theirs.pk).exists())
        self.assertEqual(self.client.get(reverse("accounts:users")).status_code, 403)

    def test_a_hiring_manager_has_full_access_and_can_also_interview(self):
        manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER)
        self.client.force_authenticate(self.recruiter)
        self.add_slot(self.recruiter)
        self.interview_for(self.recruiter, "Rida's Candidate")
        own = self.interview_for(manager, "Manager's Candidate", hours=2)
        self.client.force_authenticate(manager)
        self.assertEqual(len(self.client.get(reverse("scheduling:availability"), {"interviewer": self.recruiter.pk}).data), 1)
        self.assertEqual(len(self.client.get(reverse("scheduling:interviews")).data), 2)
        assigned = self.client.get(reverse("scheduling:interviews"), {"mine": "1"}).data
        self.assertEqual([i["public_id"] for i in assigned], [str(own.public_id)])
        self.assertEqual(self.add_slot(manager, interviewer=self.recruiter.pk, start_time="14:00", end_time="15:00").status_code, 201)
