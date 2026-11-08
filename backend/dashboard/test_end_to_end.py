"""AC-11: synthetic end-to-end run from JD/resume intake to a sent interview invitation.

Every step goes through the public REST API used by the React frontend. Only the external providers
(Azure OpenAI, ElevenLabs/Twilio, SMTP) are replaced by fakes; all human gates are exercised.
"""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateStatus
from candidates.tests import make_docx
from scoring.tests import scoring_result
from screening.tests import TRANSCRIPT, FakeLLM, FakeVoiceClient, analysis_output

RESUME_TEXT = (
    "Controls engineer. Skills: PLC and SCADA. Five years of controls engineering experience. "
    "Completed multiple industrial automation projects. Daily work using Allen-Bradley controls."
)


class FakeScoringLLM:
    deployment_name = "gpt-5-mini-test"

    def generate_structured(self, messages, response_model, **kwargs):
        return scoring_result()


class EndToEndHiringFlowTest(APITestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        overrides = override_settings(
            MEDIA_ROOT=self.temp.name,
            LANGGRAPH_CHECKPOINT_DB_PATH=Path(self.temp.name) / "checkpoints.sqlite3",
            SCREENING_CALL_WINDOW_START_HOUR=0, SCREENING_CALL_WINDOW_END_HOUR=24,
            SCREENING_VOICE_MODE="telephony",  # this flow exercises the optional phone-call route
        )
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER,
                                                first_name="Hina", last_name="Malik")

    def ok(self, response, code=200):
        self.assertEqual(response.status_code, code, getattr(response, "data", response.content))
        return response.data

    def test_complete_flow_with_all_human_gates(self):
        client = self.client
        client.force_authenticate(self.recruiter)

        # 1. Requisition (FR-01)
        requisition = self.ok(client.post("/api/v1/requisitions/", {
            "title": "Controls Engineer", "department": "Engineering", "description": "Maintain PLC/SCADA systems.",
            "required_skills": ["PLC", "SCADA"], "screening_questions": ["Years of PLC experience?", "Notice period?"],
            "hiring_manager": self.manager.pk, "status": "OPEN",
        }, format="json"), 201)

        # 2. Candidate + resume intake and extraction (FR-02)
        candidate = self.ok(client.post("/api/v1/candidates/", {
            "requisition": requisition["id"], "full_name": "Ali Raza", "email": "ali@example.test", "phone": "0300 1234567",
        }, format="json"), 201)
        cid = candidate["public_id"]
        resume = self.ok(client.post(f"/api/v1/candidates/{cid}/resumes/", {"file": make_docx(text=RESUME_TEXT)}, format="multipart"), 201)
        self.assertEqual(self.ok(client.post(f"/api/v1/candidates/resume-documents/{resume['public_id']}/process/"))["processing_status"], "COMPLETED")

        # 3. Scoring via the LangGraph workflow (FR-03), paused for HR
        with patch("scoring.services.agent.get_llm_provider", return_value=FakeScoringLLM()):
            run = self.ok(client.post(f"/api/v1/workflows/candidates/{cid}/start-scoring/"), 202)
        self.assertEqual(run["status"], "WAITING_HR_REVIEW")
        self.assertEqual(Candidate.objects.get(public_id=cid).current_status, CandidateStatus.SCORED_HR_REVIEW)

        # 4. Human gate 1: shortlist (FR-04, AC-04)
        queue = self.ok(client.get("/api/v1/reviews/shortlist/"))
        evaluation = queue["results"][0]["evaluation"]
        self.assertIsNotNone(evaluation["overall_score"])
        self.ok(client.post(f"/api/v1/reviews/candidates/{cid}/shortlist/", {
            "evaluation": evaluation["public_id"], "decision": "APPROVE_FOR_SCREENING", "decision_reason": "Strong PLC evidence",
        }, format="json"), 201)
        self.assertEqual(self.ok(client.get(f"/api/v1/workflows/{run['public_id']}/"))["status"], "COMPLETED")

        # 5. AI screening call (FR-05/06/07) with fake Twilio/ElevenLabs + fake Azure analysis
        voice = FakeVoiceClient(conversation={"status": "done", "transcript": TRANSCRIPT, "metadata": {"call_duration_secs": 120}},
                                twilio={"status": "completed"})
        with patch("screening.services.calls.get_voice_client", return_value=voice):
            screening = self.ok(client.post(f"/api/v1/screening/candidates/{cid}/", {"channel": "AI_VOICE", "start_call_now": True}, format="json"), 201)
            self.assertIsNone(screening["call_error"])
            self.assertEqual(voice.started[0][0], "+923001234567")
            with patch("screening.services.analysis.get_llm_provider", return_value=FakeLLM(analysis_output())):
                screening = self.ok(client.post(f"/api/v1/screening/{screening['public_id']}/sync/"))
        self.assertEqual(screening["status"], "AWAITING_HR_REVIEW")

        # 6. Human gate 2: screening review (FR-08)
        self.ok(client.post(f"/api/v1/screening/{screening['public_id']}/review/", {"decision": "APPROVE_FOR_INTERVIEW"}, format="json"), 201)

        # 7. Availability and scheduling (FR-09)
        day = str((timezone.now() + timedelta(days=3)).date())
        client.force_authenticate(self.manager)
        self.ok(client.post("/api/v1/scheduling/availability/", {"date": day, "start_time": "10:00", "end_time": "13:00", "timezone": "Asia/Karachi"}, format="json"), 201)
        client.force_authenticate(self.recruiter)
        interview = self.ok(client.post(f"/api/v1/scheduling/candidates/{cid}/interviews/", {
            "interviewer": self.manager.pk, "duration_minutes": 45, "timezone": "Asia/Karachi", "mode": "VIDEO",
            "meeting_link": "https://meet.example.test/e2e", "candidate_windows": [{"date": day, "start_time": "11:00", "end_time": "15:00"}],
        }, format="json"), 201)
        self.assertEqual(interview["status"], "PROPOSED")
        iid = interview["public_id"]
        self.ok(client.post(f"/api/v1/scheduling/interviews/{iid}/confirm-slot/", {
            "slot_start": interview["proposed_slots"][0]["start"], "candidate_confirmed": True, "interviewer_confirmed": True,
        }, format="json"))

        # 8. Human gate 3: invitation draft, approval and idempotent send (FR-10/11, AC-08)
        draft = self.ok(client.post(f"/api/v1/communications/interviews/{iid}/draft/"), 201)
        self.assertEqual(len(mail.outbox), 0)
        sent = self.ok(client.post(f"/api/v1/communications/{draft['public_id']}/approve-send/", {"confirm": True}, format="json"))
        self.assertEqual(sent["send_status"], "SENT")
        self.assertEqual(client.post(f"/api/v1/communications/{draft['public_id']}/approve-send/", {"confirm": True}, format="json").status_code, 400)
        self.assertEqual(len(mail.outbox), 1)

        # 9. Lifecycle and audit trail (FR-12, FR-14, AC-09)
        self.assertEqual(Candidate.objects.get(public_id=cid).current_status, CandidateStatus.INTERVIEW_SCHEDULED)
        events = {e["event_type"] for e in self.ok(client.get(f"/api/v1/candidates/{cid}/events/"))}
        for expected in ("RESUME_UPLOADED", "RESUME_SCORED", "SHORTLIST_DECISION_RECORDED", "SCREENING_CALL_STARTED",
                         "SCREENING_RESULT_RECORDED", "SCREENING_DECISION_RECORDED", "INTERVIEW_SLOTS_PROPOSED",
                         "INVITATION_APPROVED", "INVITATION_SENT"):
            self.assertIn(expected, events)
        summary = self.ok(client.get(reverse("dashboard:summary")))
        self.assertEqual(len(summary["upcoming_interviews"]), 1)
        self.assertTrue(self.ok(client.get("/api/v1/audit/"))["count"] >= 1)  # requisition creation audited


class PrivacyTests(APITestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        overrides = override_settings(MEDIA_ROOT=self.temp.name)
        overrides.enable()
        self.addCleanup(overrides.disable)
        self.admin = User.objects.create_user("adm", "adm@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.HIRING_MANAGER)
        self.client.force_authenticate(self.recruiter)
        requisition = self.client.post("/api/v1/requisitions/", {"title": "X", "department": "Y", "description": "Z", "status": "OPEN"}, format="json").data
        self.cid = self.client.post("/api/v1/candidates/", {"requisition": requisition["id"], "full_name": "Zara Shah", "email": "zara@example.test"}, format="json").data["public_id"]
        self.client.post(f"/api/v1/candidates/{self.cid}/resumes/", {"file": make_docx(text=RESUME_TEXT)}, format="multipart")

    def test_close_then_erase_personal_data(self):
        self.assertEqual(self.client.post(f"/api/v1/candidates/{self.cid}/erase-personal-data/", {"reason": "request"}, format="json").status_code, 403)
        self.assertEqual(self.client.post(f"/api/v1/candidates/{self.cid}/close/", {}, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/v1/candidates/{self.cid}/close/", {"reason": "Withdrew"}, format="json").status_code, 200)
        self.client.force_authenticate(self.admin)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f"/api/v1/candidates/{self.cid}/erase-personal-data/", {"reason": "Deletion request"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        candidate = Candidate.objects.get(public_id=self.cid)
        self.assertEqual((candidate.full_name, candidate.email), ("", None))
        self.assertIsNotNone(candidate.personal_data_erased_at)
        document = candidate.resume_documents.get()
        self.assertEqual((document.extracted_text, document.original_filename, bool(document.file)), ("", "erased", False))
        self.assertEqual(list(Path(self.temp.name).rglob("*.docx")), [])
        self.assertEqual(self.client.patch(f"/api/v1/candidates/{self.cid}/", {"full_name": "Back"}, format="json").status_code, 400)
        audit = self.client.get("/api/v1/audit/", {"action": "CANDIDATE_PERSONAL_DATA_ERASED"}).data
        self.assertEqual(audit["count"], 1)
