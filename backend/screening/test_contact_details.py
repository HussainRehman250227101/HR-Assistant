"""Missing name/email/phone are asked for by the screening agent (only when absent) and saved after the call."""

from django.test import TestCase

from candidates.models import Candidate, CandidateEvent
from . import script
from .models import Screening, ScreeningChannel
from .schemas import CollectedContactDetails
from .services import calls
from .services.analysis import candidate_text, format_transcript, verify_analysis
from .tests import FakeLLM, ScreeningFixture, analysis_output

TRANSCRIPT = [
    {"role": "agent", "message": "I am an AI assistant. May I have your email address?"},
    {"role": "user", "message": "It is sara dot ahmed at example dot test"},
    {"role": "agent", "message": "And your full name?"},
    {"role": "user", "message": "My name is Sara Ahmed"},
]


def collected(**kw):
    data = dict(full_name="", full_name_statement="", email="", email_statement="", phone="", phone_statement="")
    data.update(kw)
    return CollectedContactDetails(**data)


class ContactDetailsScriptTests(ScreeningFixture, TestCase):
    def setUp(self):
        self.make_fixture()

    def screening(self):
        return Screening.objects.create(
            candidate=self.candidate, requisition=self.requisition, channel=ScreeningChannel.BROWSER_VOICE,
            questions=["Q1"], script_version=script.BROWSER_SCRIPT_VERSION, created_by=self.recruiter)

    def test_nothing_missing_means_agent_asks_for_nothing(self):
        variables = script.build_browser_dynamic_variables(self.screening(), "Org", "hr@example.test")
        self.assertEqual(variables["missing_contact_details"], "none")

    def test_only_missing_fields_are_listed(self):
        Candidate.objects.filter(pk=self.candidate.pk).update(email=None, phone="")
        self.candidate.refresh_from_db()
        variables = script.build_dynamic_variables(self.screening(), "Org", "hr@example.test")
        self.assertEqual(variables["missing_contact_details"], "email address, phone number")
        self.assertIn("{{missing_contact_details}}", script.BROWSER_AGENT_SYSTEM_PROMPT)
        self.assertIn("{{missing_contact_details}}", script.AGENT_SYSTEM_PROMPT)


class ContactDetailsSaveTests(ScreeningFixture, TestCase):
    def setUp(self):
        self.make_fixture()
        Candidate.objects.filter(pk=self.candidate.pk).update(full_name="", email=None, identity_review_required=True)
        self.candidate.refresh_from_db()
        self.evidence = candidate_text(format_transcript(TRANSCRIPT, self.candidate))

    def verify(self, details, missing=("full_name", "email")):
        result, warnings = verify_analysis(analysis_output(collected_contact_details=details), [], self.evidence, missing)
        return result["collected_contact_details"], warnings

    def test_verified_values_are_kept_and_unverified_dropped(self):
        got, _ = self.verify(collected(full_name="Sara Ahmed", full_name_statement="My name is Sara Ahmed",
                                       email="sara.ahmed@example.test", email_statement="sara dot ahmed at example dot test"))
        self.assertEqual(got, {"full_name": "Sara Ahmed", "email": "sara.ahmed@example.test"})
        got, warnings = self.verify(collected(email="x@example.test", email_statement="never said this"))
        self.assertEqual(got, {})
        self.assertTrue(warnings)

    def test_field_not_missing_is_never_collected(self):
        got, _ = self.verify(collected(full_name="Sara Ahmed", full_name_statement="My name is Sara Ahmed"), missing=("email",))
        self.assertEqual(got, {})

    def test_invalid_email_is_not_saved(self):
        got, _ = self.verify(collected(email="not-an-email", email_statement="sara dot ahmed at example dot test"))
        self.assertEqual(got, {})

    def test_run_analysis_fills_empty_fields_and_keeps_existing(self):
        Candidate.objects.filter(pk=self.candidate.pk).update(phone="+923001234567")
        screening = Screening.objects.create(
            candidate=self.candidate, requisition=self.requisition, channel=ScreeningChannel.BROWSER_VOICE,
            questions=["Q1"], script_version=script.BROWSER_SCRIPT_VERSION, created_by=self.recruiter, transcript=TRANSCRIPT)
        output = analysis_output(
            question_answers=[],
            collected_contact_details=collected(
                full_name="Sara Ahmed", full_name_statement="My name is Sara Ahmed",
                email="sara.ahmed@example.test", email_statement="sara dot ahmed at example dot test",
                phone="+920000000000", phone_statement="My name is Sara Ahmed"))
        calls.run_analysis(screening, self.recruiter, provider=FakeLLM(output))
        c = Candidate.objects.get(pk=self.candidate.pk)
        self.assertEqual((c.full_name, c.email, c.phone), ("Sara Ahmed", "sara.ahmed@example.test", "+923001234567"))
        self.assertFalse(c.identity_review_required)
        self.assertEqual(sorted(c.auto_filled_fields), ["email", "full_name"])
        event = c.events.get(event_type=CandidateEvent.EventType.CANDIDATE_DETAILS_FROM_SCREENING)
        self.assertEqual(sorted(event.details["fields"]), ["email", "full_name"])
