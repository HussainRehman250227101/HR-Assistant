"""Candidate details read from the resume (no manual entry). Azure is mocked; no network."""

import tempfile
from io import BytesIO
from unittest.mock import Mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from docx import Document
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from requisitions.models import Requisition, RequisitionStatus
from scoring.services.agent import _redact_contact_details
from .models import Candidate, CandidateEvent, ResumeDocument, ResumeProcessingStatus
from .services.contact_details import ResumeIdentity, detect_details, fill_candidate_details_from_resume, heuristic_name
from .services.processing import process_resume_document
from .validators import DOCX_MIME

RESUME = """AYESHA KHAN
Lahore, Pakistan | ayesha.khan@example.test | +92 300 1234567
linkedin.com/in/ayesha-khan-dev

Summary
Backend developer with five years of Django and PostgreSQL experience.

References
Dr. Imran Ali, imran.ali@example.test, +92 321 7654321
"""


def ai(full_name="Ayesha Khan", location="Lahore, Pakistan"):
    provider = Mock()
    provider.is_configured = True
    provider.generate_structured.return_value = ResumeIdentity(full_name=full_name, location=location)
    return provider


def no_ai():
    provider = Mock()
    provider.is_configured = False
    return provider


class DetectDetailsTests(TestCase):
    def test_reads_own_details_and_ignores_the_referee(self):
        details, source = detect_details(RESUME, provider=ai())
        self.assertEqual(details["full_name"], "Ayesha Khan")
        self.assertEqual(details["email"], "ayesha.khan@example.test")
        self.assertEqual(details["phone"], "+923001234567")
        self.assertEqual(details["location"], "Lahore, Pakistan")
        self.assertEqual(details["linkedin_url"], "https://linkedin.com/in/ayesha-khan-dev")
        self.assertEqual(source, "ai")

    def test_ai_values_not_in_the_resume_are_discarded(self):
        details, source = detect_details(RESUME, provider=ai(full_name="Sara Ahmed", location="Karachi"))
        self.assertEqual(details["full_name"], "Ayesha Khan")  # local rule, not the invented AI value
        self.assertEqual(source, "heuristic")
        self.assertNotIn("location", details)

    def test_without_azure_the_name_comes_from_the_top_line(self):
        details, source = detect_details(RESUME, provider=no_ai())
        self.assertEqual((details["full_name"], source), ("Ayesha Khan", "heuristic"))
        self.assertNotIn("location", details)
        self.assertIsNone(heuristic_name("Curriculum Vitae\nSummary\nPython developer"))

    def test_ambiguous_contacts_far_from_the_top_are_not_guessed(self):
        text = "Ayesha Khan\n" + ("Experience line.\n" * 300) + "a@example.test\nb@example.test\n"
        details, _ = detect_details(text, provider=no_ai())
        self.assertNotIn("email", details)

    def test_azure_receives_only_the_top_of_the_resume(self):
        provider = ai()
        detect_details(RESUME + ("x " * 5000), provider=provider)
        user_message = provider.generate_structured.call_args.kwargs["messages"][-1]["content"]
        self.assertLess(len(user_message), 2600)


class FillCandidateDetailsTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(
            username="details-recruiter", email="details@example.test",
            password="Strong-Test-Password-123!", role=UserRole.ADMIN,
        )
        self.requisition = Requisition.objects.create(
            title="Backend Developer", department="Engineering", description="Django role.",
            status=RequisitionStatus.OPEN, created_by=self.recruiter,
        )

    def _placeholder(self, text=RESUME, **fields):
        candidate = Candidate.objects.create(
            requisition=self.requisition, identity_review_required=True, created_by=self.recruiter, **fields,
        )
        document = ResumeDocument.objects.create(
            candidate=candidate, file="resumes/x.docx", original_filename="x.docx", content_type=DOCX_MIME,
            file_size=10, sha256=f"{Candidate.objects.count():064d}",
            processing_status=ResumeProcessingStatus.COMPLETED, extracted_text=text, created_by=self.recruiter,
        )
        return candidate, document

    def test_placeholder_gets_details_and_no_longer_needs_review(self):
        candidate, document = self._placeholder()
        filled = fill_candidate_details_from_resume(document, provider=ai())
        candidate.refresh_from_db()
        self.assertEqual(set(filled), {"full_name", "email", "phone", "location", "linkedin_url"})
        self.assertEqual(candidate.full_name, "Ayesha Khan")
        self.assertFalse(candidate.identity_review_required)
        self.assertEqual(set(candidate.auto_filled_fields), set(filled))
        event = CandidateEvent.objects.get(candidate=candidate, event_type=CandidateEvent.EventType.CANDIDATE_DETAILS_FROM_RESUME)
        self.assertEqual(set(event.details["fields"]), set(filled))
        self.assertNotIn("ayesha", str(event.details).lower())  # field names only, never values

    def test_values_entered_by_hr_are_never_overwritten(self):
        candidate, document = self._placeholder(full_name="Ayesha K. Khan", phone="+923009999999")
        fill_candidate_details_from_resume(document, provider=ai())
        candidate.refresh_from_db()
        self.assertEqual((candidate.full_name, candidate.phone), ("Ayesha K. Khan", "+923009999999"))
        self.assertNotIn("full_name", candidate.auto_filled_fields)

    def test_duplicate_email_in_the_requisition_is_flagged_not_filled(self):
        Candidate.objects.create(requisition=self.requisition, full_name="Earlier application",
                                 email="ayesha.khan@example.test", created_by=self.recruiter)
        candidate, document = self._placeholder(text="Ayesha Khan\nayesha.khan@example.test\n")
        fill_candidate_details_from_resume(document, provider=no_ai())
        candidate.refresh_from_db()
        self.assertIsNone(candidate.email)
        self.assertTrue(candidate.identity_review_required)
        event = CandidateEvent.objects.get(candidate=candidate, event_type=CandidateEvent.EventType.CANDIDATE_DETAILS_FROM_RESUME)
        self.assertTrue(event.details["possible_duplicate_email"])

    def test_resume_without_contact_details_keeps_the_review_flag(self):
        candidate, document = self._placeholder(text="Ayesha Khan\nBackend developer.\n")
        fill_candidate_details_from_resume(document, provider=no_ai())
        candidate.refresh_from_db()
        self.assertEqual(candidate.full_name, "Ayesha Khan")
        self.assertTrue(candidate.identity_review_required)

    def test_editing_a_field_removes_its_from_resume_mark(self):
        candidate, document = self._placeholder()
        fill_candidate_details_from_resume(document, provider=ai())
        client = APIClient()
        client.force_authenticate(self.recruiter)
        response = client.patch(f"/api/v1/candidates/{candidate.public_id}/", {"phone": "+923005555555"}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotIn("phone", response.data["auto_filled_fields"])
        self.assertIn("email", response.data["auto_filled_fields"])

    def test_scoring_redacts_the_detected_identity(self):
        candidate, document = self._placeholder()
        fill_candidate_details_from_resume(document, provider=ai())
        candidate.refresh_from_db()
        redacted = _redact_contact_details(RESUME, candidate)
        for value in ("AYESHA KHAN", "ayesha.khan@example.test", "300 1234567", "linkedin.com", "Lahore, Pakistan"):
            self.assertNotIn(value.lower(), redacted.lower())

    def test_extraction_fills_details_before_scoring(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as media:
            with override_settings(MEDIA_ROOT=media):
                buffer = BytesIO()
                docx = Document()
                for line in RESUME.splitlines():
                    docx.add_paragraph(line)
                docx.save(buffer)
                candidate = Candidate.objects.create(requisition=self.requisition, identity_review_required=True,
                                                     created_by=self.recruiter)
                document = ResumeDocument.objects.create(
                    candidate=candidate, file=SimpleUploadedFile("cv.docx", buffer.getvalue(), content_type=DOCX_MIME),
                    original_filename="cv.docx", content_type=DOCX_MIME, file_size=len(buffer.getvalue()),
                    sha256="f" * 64, created_by=self.recruiter,
                )
                # The test runner blanks Azure settings, so only local detection runs here.
                processed = process_resume_document(document, actor=self.recruiter)
        candidate.refresh_from_db()
        self.assertEqual(processed.processing_status, ResumeProcessingStatus.COMPLETED)
        self.assertEqual(candidate.full_name, "Ayesha Khan")
        self.assertEqual(candidate.email, "ayesha.khan@example.test")
        self.assertFalse(candidate.identity_review_required)
