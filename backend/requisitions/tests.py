from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from .models import Requisition, RequisitionStatus


class RequisitionAPITests(APITestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(
            username="recruiter", email="recruiter@example.test",
            password="Strong-Test-Password-123!", role=UserRole.ADMIN,
        )
        self.manager = User.objects.create_user(
            username="manager", email="manager@example.test",
            password="Strong-Test-Password-123!", role=UserRole.HIRING_MANAGER,
        )
        self.other_manager = User.objects.create_user(
            username="manager2", email="manager2@example.test",
            password="Strong-Test-Password-123!", role=UserRole.HIRING_MANAGER,
        )
        self.admin = User.objects.create_user(
            username="hradmin", email="hradmin@example.test",
            password="Strong-Test-Password-123!", role=UserRole.ADMIN,
        )
        self.list_url = reverse("requisitions:requisition-list")
        self.payload = {
            "title": "Senior Controls Engineer",
            "department": "Engineering",
            "location": "Lahore, Pakistan",
            "employment_type": "FULL_TIME",
            "work_mode": "HYBRID",
            "description": "Design, develop and support industrial control systems.",
            "responsibilities": "Own PLC and SCADA engineering deliverables.",
            "required_skills": ["PLC", "SCADA", "FAT"],
            "preferred_skills": ["Python", "FactoryTalk"],
            "screening_questions": ["Describe your PLC commissioning experience."],
            "minimum_experience_years": "5.0",
            "education_requirements": "Bachelor's degree in Engineering.",
            "salary_min": "200000.00",
            "salary_max": "350000.00",
            "currency": "PKR",
            "headcount": 1,
            "status": "DRAFT",
            "hiring_manager": self.manager.id,
            "target_close_date": "2026-12-31",
        }

    def create_requisition(self, **overrides):
        values = {**self.payload, **overrides}
        return Requisition.objects.create(
            title=values["title"],
            department=values["department"],
            description=values["description"],
            created_by=self.recruiter,
            hiring_manager=values.get("hiring_manager") and User.objects.get(
                id=values["hiring_manager"]
            ),
            status=values.get("status", RequisitionStatus.DRAFT),
        )

    def test_anonymous_user_cannot_list_requisitions(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_recruiter_can_create_requisition_and_creator_is_server_assigned(self):
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        requisition = Requisition.objects.get()
        self.assertEqual(requisition.created_by, self.recruiter)
        self.assertEqual(requisition.hiring_manager, self.manager)
        self.assertEqual(requisition.status, RequisitionStatus.DRAFT)
        self.assertTrue(response.data["reference_code"])
        self.assertEqual(requisition.preferred_skills, ["Python", "FactoryTalk"])
        self.assertEqual(requisition.screening_questions, ["Describe your PLC commissioning experience."])

    def test_interview_format_defaults_to_onsite_and_video_requires_a_whatsapp_number(self):
        self.client.force_authenticate(user=self.recruiter)
        created = self.client.post(self.list_url, {**self.payload, "interview_format": "ONSITE"}, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data["interview_format"], "ONSITE")
        self.assertEqual(created.data["interview_whatsapp_number"], "")
        missing = self.client.post(self.list_url, {**self.payload, "interview_format": "VIDEO"}, format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("interview_whatsapp_number", missing.data)
        bad = self.client.post(
            self.list_url, {**self.payload, "interview_format": "VIDEO", "interview_whatsapp_number": "call me"}, format="json")
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        video = self.client.post(
            self.list_url,
            {**self.payload, "interview_format": "VIDEO", "interview_whatsapp_number": "+92 300-1234567"}, format="json")
        self.assertEqual(video.status_code, status.HTTP_201_CREATED, video.data)
        self.assertEqual(video.data["interview_whatsapp_number"], "+923001234567")

    def test_onsite_format_needs_a_location_and_drops_a_stray_whatsapp_number(self):
        self.client.force_authenticate(user=self.recruiter)
        no_location = self.client.post(
            self.list_url, {**self.payload, "location": "", "interview_format": "ONSITE"}, format="json")
        self.assertEqual(no_location.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("location", no_location.data)
        stray = self.client.post(
            self.list_url,
            {**self.payload, "interview_format": "ONSITE", "interview_whatsapp_number": "+923001234567"}, format="json")
        self.assertEqual(stray.status_code, status.HTTP_201_CREATED, stray.data)
        self.assertEqual(stray.data["interview_whatsapp_number"], "")

    def test_hiring_manager_sees_every_requisition(self):
        assigned = self.create_requisition()
        other = self.create_requisition(
            title="Automation Engineer", hiring_manager=self.other_manager.id
        )
        self.client.force_authenticate(user=self.manager)
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        result_codes = {item["reference_code"] for item in response.data["results"]}
        self.assertEqual(result_codes, {str(assigned.reference_code), str(other.reference_code)})
        created = self.client.post(self.list_url, self.payload, format="json")
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

    def test_recruiter_interviewer_sees_only_requisitions_of_assigned_candidates(self):
        from datetime import timedelta
        from django.utils import timezone
        from candidates.models import Candidate
        from scheduling.models import Interview
        interviewer = User.objects.create_user(
            username="interviewer", email="interviewer@example.test",
            password="Strong-Test-Password-123!", role=UserRole.RECRUITER,
        )
        assigned = self.create_requisition()
        other = self.create_requisition(title="Automation Engineer")
        candidate = Candidate.objects.create(requisition=assigned, full_name="A Candidate", created_by=self.admin)
        start = timezone.now() + timedelta(days=2)
        Interview.objects.create(
            candidate=candidate, requisition=assigned, interviewer=interviewer, timezone="Asia/Karachi", status="SCHEDULED",
            confirmed_start=start, confirmed_end=start + timedelta(minutes=45), mode="ONSITE", location="Office", created_by=self.admin,
        )
        self.client.force_authenticate(user=interviewer)
        response = self.client.get(self.list_url)
        self.assertEqual({i["reference_code"] for i in response.data["results"]}, {str(assigned.reference_code)})
        hidden = self.client.get(reverse("requisitions:requisition-detail", args=[other.reference_code]))
        self.assertEqual(hidden.status_code, status.HTTP_404_NOT_FOUND)

    def test_recruiter_interviewer_cannot_create_or_edit_requisitions(self):
        requisition = self.create_requisition()
        interviewer = User.objects.create_user(
            username="interviewer2", email="interviewer2@example.test",
            password="Strong-Test-Password-123!", role=UserRole.RECRUITER,
        )
        self.client.force_authenticate(user=interviewer)
        create_response = self.client.post(self.list_url, self.payload, format="json")
        update_response = self.client.patch(
            reverse("requisitions:requisition-detail", args=[requisition.reference_code]),
            {"title": "Changed title"}, format="json",
        )
        self.assertEqual(create_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_recruiter_can_open_a_draft_and_system_sets_opened_at(self):
        requisition = self.create_requisition()
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            reverse("requisitions:requisition-detail", args=[requisition.reference_code]),
            {"status": "OPEN"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        requisition.refresh_from_db()
        self.assertIsNotNone(requisition.opened_at)
        self.assertEqual(requisition.status, RequisitionStatus.OPEN)

    def test_closed_requisition_cannot_be_reopened(self):
        requisition = self.create_requisition(status=RequisitionStatus.CLOSED)
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.patch(
            reverse("requisitions:requisition-detail", args=[requisition.reference_code]),
            {"status": "OPEN"}, format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_salary_minimum_cannot_exceed_maximum(self):
        self.client.force_authenticate(user=self.recruiter)
        payload = {**self.payload, "salary_min": "400000.00", "salary_max": "300000.00"}
        response = self.client.post(self.list_url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("salary_max", response.data)

    def test_status_and_department_filters_work(self):
        self.create_requisition(status=RequisitionStatus.DRAFT)
        self.create_requisition(
            title="Automation Engineer",
            status=RequisitionStatus.OPEN,
            hiring_manager=self.manager.id,
        )
        self.client.force_authenticate(user=self.recruiter)
        response = self.client.get(self.list_url, {"status": "OPEN", "department": "Engineering"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Automation Engineer")

    def test_only_draft_requisitions_can_be_deleted(self):
        draft = self.create_requisition()
        opened = self.create_requisition(
            title="Open role", status=RequisitionStatus.OPEN,
        )
        self.client.force_authenticate(user=self.recruiter)
        draft_response = self.client.delete(
            reverse("requisitions:requisition-detail", args=[draft.reference_code])
        )
        opened_response = self.client.delete(
            reverse("requisitions:requisition-detail", args=[opened.reference_code])
        )
        self.assertEqual(draft_response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(opened_response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_hr_admin_can_access_all_requisitions(self):
        assigned_to_other = self.create_requisition(hiring_manager=self.other_manager.id)
        self.client.force_authenticate(user=self.admin)
        response = self.client.get(
            reverse("requisitions:requisition-detail", args=[assigned_to_other.reference_code])
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
