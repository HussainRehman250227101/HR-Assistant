from datetime import datetime, time, timedelta

from django.core import mail
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateStatus
from requisitions.models import Requisition, RequisitionStatus
from scheduling.models import AvailabilitySlot, InterviewStatus
from scheduling.services.interviews import cancel_interview, confirm_slot, plan_interview, repropose
from scheduling.services.slots import local_window_to_utc
from .models import CommunicationLog, SendStatus
from .services import CommunicationError, approve_and_send, draft_message


class FailingConnection:
    def send_messages(self, messages):
        raise OSError("SMTP down")


class InvitationTests(APITestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER,
                                                first_name="Hina", last_name="Malik")
        self.requisition = Requisition.objects.create(title="Backend Engineer", department="Eng", description="APIs",
                                                      status=RequisitionStatus.OPEN, created_by=self.recruiter)
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Sara Ahmed", email="sara@example.test", phone="03001234567",
            current_status=CandidateStatus.APPROVED_FOR_INTERVIEW, created_by=self.recruiter)
        self.day = (timezone.now() + timedelta(days=3)).date()
        start, end = local_window_to_utc(self.day, time(9), time(17), "Asia/Karachi")
        AvailabilitySlot.objects.create(interviewer=self.manager, start=start, end=end, timezone="Asia/Karachi", created_by=self.manager)
        c_start, c_end = local_window_to_utc(self.day, time(10), time(16), "Asia/Karachi")
        self.interview = plan_interview(self.candidate, self.recruiter, {
            "interviewer": self.manager, "duration_minutes": 45, "timezone": "Asia/Karachi", "mode": "VIDEO",
            "meeting_link": "https://meet.example.test/xyz",
            "candidate_windows": [{"start": c_start.isoformat(), "end": c_end.isoformat()}]})
        slot = datetime.fromisoformat(self.interview.proposed_slots[0]["start"])
        confirm_slot(self.interview, self.recruiter, slot, True, True)
        self.client.force_authenticate(self.recruiter)

    def test_draft_requires_confirmed_slot_and_contains_required_fields(self):
        log = draft_message(self.interview, self.recruiter)
        self.assertEqual(draft_message(self.interview, self.recruiter).pk, log.pk)  # idempotent
        for text in ("Backend Engineer", "Asia/Karachi", "45 minutes", "https://meet.example.test/xyz", "Hina Malik", "reschedule"):
            self.assertIn(text, log.body)
        self.assertEqual(log.send_status, SendStatus.NOT_SENT)
        self.assertEqual(len(mail.outbox), 0)  # drafting never sends

    def test_send_requires_explicit_approval_and_happens_once(self):
        log = draft_message(self.interview, self.recruiter)
        url = reverse("communications:approve-send", args=[log.public_id])
        self.assertEqual(self.client.post(url, {"confirm": False}, format="json").status_code, 400)
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(url, {"confirm": True}, format="json").status_code, 403)
        self.client.force_authenticate(self.recruiter)
        response = self.client.post(url, {"confirm": True}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["send_status"], "SENT")
        self.assertEqual(response.data["approved_by_name"], "rec")
        self.assertTrue(response.data["provider_message_id"])
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["sara@example.test"])
        self.assertIn("hm@example.test", message.cc)
        self.assertIn("METHOD:REQUEST", message.attachments[0][1])
        self.interview.refresh_from_db()
        self.candidate.refresh_from_db()
        self.assertEqual(self.interview.status, InterviewStatus.SCHEDULED)
        self.assertEqual(self.candidate.current_status, CandidateStatus.INTERVIEW_SCHEDULED)
        self.assertEqual(self.client.post(url, {"confirm": True}, format="json").status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

    def test_failure_keeps_draft_and_never_claims_sent(self):
        log = draft_message(self.interview, self.recruiter)
        with self.assertRaises(CommunicationError):
            approve_and_send(log, self.recruiter, connection=FailingConnection())
        log.refresh_from_db()
        self.interview.refresh_from_db()
        self.assertEqual(log.send_status, SendStatus.FAILED)
        self.assertEqual(log.approval_status, "APPROVED")
        self.assertEqual(self.interview.status, InterviewStatus.SLOT_CONFIRMED)
        approve_and_send(log, self.recruiter)  # safe retry after the failure
        log.refresh_from_db()
        self.assertEqual(log.send_status, SendStatus.SENT)
        self.assertEqual(log.send_attempts, 2)

    def test_edit_cannot_remove_required_details(self):
        log = draft_message(self.interview, self.recruiter)
        self.client.patch(reverse("communications:detail", args=[log.public_id]),
                          {"subject": "Interview", "body": "Please come in."}, format="json")
        response = self.client.post(reverse("communications:approve-send", args=[log.public_id]), {"confirm": True}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("required details", str(response.data))

    def test_reschedule_and_cancellation_updates(self):
        approve_and_send(draft_message(self.interview, self.recruiter), self.recruiter)
        self.interview.refresh_from_db()
        repropose(self.interview, self.recruiter, {})
        self.interview.refresh_from_db()
        self.assertEqual(self.interview.sequence, 1)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.INTERVIEW_PROPOSED)
        new_slot = datetime.fromisoformat(self.interview.proposed_slots[1]["start"])
        confirm_slot(self.interview, self.recruiter, new_slot, True, True)
        update = draft_message(self.interview, self.recruiter)
        self.assertEqual(update.kind, "INTERVIEW_RESCHEDULE")
        approve_and_send(update, self.recruiter)
        self.assertIn("SEQUENCE:1", mail.outbox[-1].attachments[0][1])
        self.interview.refresh_from_db()
        cancel_interview(self.interview, self.recruiter, "Role on hold")
        notice = CommunicationLog.objects.get(kind="INTERVIEW_CANCELLATION")
        self.assertEqual(notice.send_status, SendStatus.NOT_SENT)  # still needs HR approval
        approve_and_send(notice, self.recruiter)
        self.assertIn("METHOD:CANCEL", mail.outbox[-1].attachments[0][1])
