from datetime import date, datetime, time, timedelta, timezone as dt_timezone

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateStatus
from requisitions.models import Requisition, RequisitionStatus
from .models import AvailabilitySlot, Interview, InterviewStatus
from .services.slots import compute_slots, local_window_to_utc


def utc(*args):
    return datetime(*args, tzinfo=dt_timezone.utc)


class Fixture:
    def make(self):
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department="Eng", description="APIs", status=RequisitionStatus.OPEN,
            created_by=self.recruiter, hiring_manager=self.manager,
        )
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Sara Ahmed", email="sara@example.test", phone="03001234567",
            current_status=CandidateStatus.APPROVED_FOR_INTERVIEW, created_by=self.recruiter,
        )
        self.day = (timezone.now() + timedelta(days=3)).date()


class SlotEngineTests(Fixture, TestCase):
    def setUp(self):
        self.make()

    def test_time_zone_conversion(self):
        start, end = local_window_to_utc(date(2026, 12, 1), time(10), time(12), "Asia/Karachi")
        self.assertEqual(start, utc(2026, 12, 1, 5))
        self.assertEqual(end, utc(2026, 12, 1, 7))

    def test_only_mutually_free_slots_are_offered(self):
        # Interviewer free 10:00-13:00 PKT; candidate free 11:00-15:00 PKT; one booked interview 11:00-11:45.
        a_start, a_end = local_window_to_utc(self.day, time(10), time(13), "Asia/Karachi")
        AvailabilitySlot.objects.create(interviewer=self.manager, start=a_start, end=a_end, timezone="Asia/Karachi", created_by=self.manager)
        other = Candidate.objects.create(requisition=self.requisition, full_name="Other", created_by=self.recruiter)
        Interview.objects.create(candidate=other, requisition=self.requisition, interviewer=self.manager, timezone="UTC",
                                 status=InterviewStatus.SCHEDULED, confirmed_start=a_start + timedelta(hours=1),
                                 confirmed_end=a_start + timedelta(hours=1, minutes=45), created_by=self.recruiter)
        c_start, c_end = local_window_to_utc(self.day, time(11), time(15), "Asia/Karachi")
        slots = compute_slots(self.manager, [(c_start, c_end)], 45)
        starts = [datetime.fromisoformat(s["start"]) for s in slots]
        # 11:00 and 11:30 clash with the booked interview; 12:00 is the first free start; 12:15 end limit -> 12:00 only.
        self.assertEqual(starts, [c_start + timedelta(hours=1)])


class InterviewAPITests(Fixture, APITestCase):
    def setUp(self):
        self.make()
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse("scheduling:availability"), {
            "date": str(self.day), "start_time": "09:00", "end_time": "12:00", "timezone": "Asia/Karachi"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.client.force_authenticate(self.recruiter)

    def plan(self, windows):
        return self.client.post(reverse("scheduling:candidate-interviews", args=[self.candidate.public_id]), {
            "interviewer": self.manager.pk, "duration_minutes": 60, "timezone": "Asia/Karachi", "mode": "VIDEO",
            "meeting_link": "https://meet.example.test/abc", "candidate_windows": windows,
        }, format="json")

    def test_propose_confirm_and_prevent_double_booking(self):
        response = self.plan([{"date": str(self.day), "start_time": "10:00", "end_time": "12:00"}])
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["status"], "PROPOSED")
        self.assertEqual(len(response.data["proposed_slots"]), 3)  # 10:00, 10:30, 11:00 PKT
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.INTERVIEW_PROPOSED)
        url = reverse("scheduling:interview-confirm-slot", args=[response.data["public_id"]])
        slot = response.data["proposed_slots"][0]["start"]
        self.assertEqual(self.client.post(url, {"slot_start": slot, "candidate_confirmed": True, "interviewer_confirmed": False}, format="json").status_code, 400)
        confirmed = self.client.post(url, {"slot_start": slot, "candidate_confirmed": True, "interviewer_confirmed": True}, format="json")
        self.assertEqual(confirmed.status_code, 200, confirmed.data)
        self.assertEqual(confirmed.data["status"], "SLOT_CONFIRMED")
        # A second candidate cannot be offered the booked hour.
        second = Candidate.objects.create(requisition=self.requisition, full_name="B", created_by=self.recruiter,
                                          current_status=CandidateStatus.APPROVED_FOR_INTERVIEW)
        other = self.client.post(reverse("scheduling:candidate-interviews", args=[second.public_id]), {
            "interviewer": self.manager.pk, "duration_minutes": 60, "timezone": "Asia/Karachi", "mode": "PHONE",
            "candidate_windows": [{"date": str(self.day), "start_time": "10:00", "end_time": "11:00"}]}, format="json")
        self.assertEqual(other.data["status"], "NEEDS_HR_COORDINATION")

    def test_no_overlap_creates_hr_task_and_cancel_restores_status(self):
        response = self.plan([{"date": str(self.day), "start_time": "15:00", "end_time": "17:00"}])
        self.assertEqual(response.data["status"], "NEEDS_HR_COORDINATION")
        self.assertEqual(response.data["proposed_slots"], [])
        cancel = self.client.post(reverse("scheduling:interview-cancel", args=[response.data["public_id"]]), {"reason": "Candidate withdrew"}, format="json")
        self.assertEqual(cancel.status_code, 200)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.APPROVED_FOR_INTERVIEW)

    def test_requires_interview_approval_and_permissions(self):
        self.candidate.current_status = CandidateStatus.SCREENING_COMPLETED_HR_REVIEW
        self.candidate.save()
        self.assertEqual(self.plan([{"date": str(self.day), "start_time": "10:00", "end_time": "12:00"}]).status_code, 400)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.plan([{"date": str(self.day), "start_time": "10:00", "end_time": "12:00"}]).status_code, 403)
        other_manager = User.objects.create_user("hm2", "hm2@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER)
        response = self.client.post(reverse("scheduling:availability"), {
            "interviewer": other_manager.pk, "date": str(self.day), "start_time": "13:00", "end_time": "14:00", "timezone": "UTC"}, format="json")
        self.assertEqual(response.status_code, 403)
