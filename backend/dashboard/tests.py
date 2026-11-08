from django.urls import reverse
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateEvent, CandidateStatus
from requisitions.models import Requisition, RequisitionStatus


class DashboardTests(APITestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER)
        mine = Requisition.objects.create(title="Mine", department="Eng", description="x", status=RequisitionStatus.OPEN,
                                          created_by=self.recruiter, hiring_manager=self.manager)
        other = Requisition.objects.create(title="Other", department="Ops", description="x", status=RequisitionStatus.OPEN,
                                           created_by=self.recruiter)
        self.a = Candidate.objects.create(requisition=mine, full_name="A", created_by=self.recruiter,
                                          current_status=CandidateStatus.SCORED_HR_REVIEW)
        Candidate.objects.create(requisition=other, full_name="B", created_by=self.recruiter,
                                 current_status=CandidateStatus.APPROVED_FOR_INTERVIEW)
        CandidateEvent.objects.create(candidate=self.a, actor=self.recruiter, event_type="STATUS_CHANGED", details={"to": "SCORED_HR_REVIEW"})

    def test_summary_counts_and_attention(self):
        self.client.force_authenticate(self.recruiter)
        data = self.client.get(reverse("dashboard:summary")).data
        self.assertEqual(data["total_candidates"], 2)
        self.assertEqual(data["open_requisitions"], 2)
        counts = {row["status"]: row["count"] for row in data["by_status"]}
        self.assertEqual(counts["SCORED_HR_REVIEW"], 1)
        self.assertEqual(len(data["by_status"]), 10)
        keys = {item["key"] for item in data["attention"]}
        self.assertIn("SHORTLIST_REVIEW", keys)
        self.assertIn("INTERVIEW_TO_PLAN", keys)

    def test_hiring_manager_sees_everything(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get(reverse("dashboard:summary")).data["total_candidates"], 2)

    def test_recruiter_interviewer_is_scoped_to_assigned_candidates(self):
        from datetime import timedelta
        from django.utils import timezone
        from scheduling.models import Interview
        interviewer = User.objects.create_user("int", "int@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        start = timezone.now() + timedelta(days=2)
        Interview.objects.create(candidate=self.a, requisition=self.a.requisition, interviewer=interviewer, timezone="UTC",
                                 status="SCHEDULED", confirmed_start=start, confirmed_end=start + timedelta(minutes=45),
                                 mode="ONSITE", location="Office", created_by=self.recruiter)
        self.client.force_authenticate(interviewer)
        summary = self.client.get(reverse("dashboard:summary")).data
        self.assertEqual((summary["total_candidates"], summary["open_requisitions"]), (1, 1))
        self.assertEqual(self.client.get(reverse("dashboard:summary")).data["total_candidates"], 1)
        pipeline = self.client.get(reverse("dashboard:pipeline")).data
        self.assertEqual([row["name"] for row in pipeline["results"]], ["A"])
        activity = self.client.get(reverse("dashboard:activity")).data
        self.assertEqual(activity["count"], 1)

    def test_pipeline_filters(self):
        self.client.force_authenticate(self.recruiter)
        rows = self.client.get(reverse("dashboard:pipeline"), {"status": "APPROVED_FOR_INTERVIEW"}).data["results"]
        self.assertEqual([r["name"] for r in rows], ["B"])
        self.assertEqual(self.client.get(reverse("dashboard:pipeline"), {"status": "BAD"}).status_code, 400)
