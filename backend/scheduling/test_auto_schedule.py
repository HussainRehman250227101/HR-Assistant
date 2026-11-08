"""Agent 3 automatic path: availability matching, on-site / WhatsApp video invitations, safe fallbacks."""

from datetime import timedelta, time
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateEvent, CandidateStatus
from communications.models import CommunicationLog, SendStatus
from requisitions.models import InterviewFormat, Requisition, RequisitionStatus
from screening.models import Screening, ScreeningDecision, ScreeningReview, ScreeningStatus
from screening.services.review import review_screening
from .models import AvailabilitySlot, Interview, InterviewMode, InterviewStatus
from .schemas import AvailabilityWindowOut, CandidateAvailabilityOut
from .services.auto import AutoScheduleOutcome, auto_schedule_candidate, candidates_awaiting_auto_schedule, safe_auto_schedule
from .services.slots import local_window_to_utc

PKT = ZoneInfo("Asia/Karachi")
LOCMEM = "django.core.mail.backends.locmem.EmailBackend"
EVENT = CandidateEvent.EventType


class FakeLLM:
    def __init__(self, output=None, error=None):
        self.output, self.error, self.calls = output, error, []

    def generate_structured(self, messages, response_model, max_completion_tokens=None):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return self.output


def stated(day, start="10:00", end="14:00", tz="Asia/Karachi"):
    return CandidateAvailabilityOut(timezone=tz, windows=[AvailabilityWindowOut(date=day.isoformat(), start_time=start, end_time=end)])


class AutoFixture:
    def make(self, interview_format=InterviewFormat.ONSITE, whatsapp=""):
        self.recruiter = User.objects.create_user("rec", "rec@example.test", "Pass-12345!", role=UserRole.ADMIN)
        self.manager = User.objects.create_user("hm", "hm@example.test", "Pass-12345!", role=UserRole.RECRUITER,
                                                first_name="Hina", last_name="Malik")
        self.requisition = Requisition.objects.create(
            title="Backend Engineer", department="Eng", description="APIs", status=RequisitionStatus.OPEN,
            location="Netsol Lahore", interview_format=interview_format, interview_whatsapp_number=whatsapp,
            screening_questions=["Years of Django?"], created_by=self.recruiter, hiring_manager=self.manager,
        )
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Sara Ahmed", email="sara@example.test",
            current_status=CandidateStatus.APPROVED_FOR_INTERVIEW, created_by=self.recruiter,
        )
        self.day = (timezone.now().astimezone(PKT) + timedelta(days=3)).date()
        self.screening = Screening.objects.create(
            candidate=self.candidate, requisition=self.requisition, status=ScreeningStatus.REVIEWED,
            questions=["Years of Django?"], script_version="v", created_by=self.recruiter,
            candidate_stated_availability="I can do the day after tomorrow, between ten and two, Pakistan time.",
            call_timestamp=timezone.now() - timedelta(hours=1),
        )
        ScreeningReview.objects.create(
            screening=self.screening, candidate=self.candidate, decision=ScreeningDecision.APPROVE_FOR_INTERVIEW,
            previous_candidate_status=CandidateStatus.SCREENING_COMPLETED_HR_REVIEW,
            resulting_candidate_status=CandidateStatus.APPROVED_FOR_INTERVIEW, decided_by=self.recruiter,
        )

    def free(self, user, start="11:00", end="13:00", day=None):
        s, e = local_window_to_utc(day or self.day, time.fromisoformat(start), time.fromisoformat(end), "Asia/Karachi")
        return AvailabilitySlot.objects.create(interviewer=user, start=s, end=e, timezone="Asia/Karachi", created_by=user)

    def go(self, llm):
        with patch("scheduling.services.auto.get_llm_provider", return_value=llm):
            return auto_schedule_candidate(self.candidate.pk)


@override_settings(EMAIL_BACKEND=LOCMEM, SCREENING_ORGANIZATION_NAME="Netsol", INTERVIEW_AUTO_SCHEDULING_ENABLED=True)
class AutoScheduleTests(AutoFixture, TestCase):
    def setUp(self):
        self.make()

    def test_onsite_interview_is_matched_booked_and_emailed_automatically(self):
        self.free(self.manager)
        llm = FakeLLM(stated(self.day))
        self.assertEqual(self.go(llm), AutoScheduleOutcome.SCHEDULED)
        interview = Interview.objects.get()
        self.assertEqual(interview.status, InterviewStatus.SCHEDULED)
        self.assertTrue(interview.auto_scheduled)
        self.assertEqual(interview.mode, InterviewMode.ONSITE)
        self.assertEqual(interview.location, "Netsol Lahore")
        self.assertEqual(interview.interviewer, self.manager)
        # Earliest overlap of candidate 10-14 and interviewer 11-13 (PKT) is 11:00 PKT.
        self.assertEqual(interview.confirmed_start.astimezone(PKT).hour, 11)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.INTERVIEW_SCHEDULED)
        self.assertEqual(len(mail.outbox), 1)
        message = mail.outbox[0]
        self.assertEqual(message.to, ["sara@example.test"])
        self.assertIn("Netsol Lahore", message.body)
        self.assertIn("on-site", message.body)
        self.assertIn("11:00", message.body)
        self.assertNotIn("WhatsApp", message.body)
        # Friendly, personal tone (first name, warm subject, inviting close).
        self.assertTrue(message.body.startswith("Hi Sara,"))
        self.assertIn("looking forward to meeting you", message.body)
        self.assertEqual(message.subject, "You're invited! Interview for Backend Engineer at Netsol")
        self.assertNotIn("Dear", message.body)
        log = CommunicationLog.objects.get()
        self.assertTrue(log.auto_sent)
        self.assertEqual(log.send_status, SendStatus.SENT)
        self.assertEqual(log.approved_by, self.recruiter)
        approved = CandidateEvent.objects.get(candidate=self.candidate, event_type=EVENT.INVITATION_APPROVED)
        self.assertTrue(approved.details["automatic"])
        # Only the availability answer is sent to the model: no name, email or phone.
        sent_text = " ".join(m["content"] for m in llm.calls[0])
        self.assertNotIn("Sara", sent_text)
        self.assertNotIn("sara@example.test", sent_text)

    def test_running_again_never_plans_or_sends_a_second_invitation(self):
        self.free(self.manager)
        self.go(FakeLLM(stated(self.day)))
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.SKIPPED)
        self.assertEqual(Interview.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_no_overlap_leaves_the_candidate_with_hr_and_sends_nothing(self):
        self.free(self.manager, day=self.day + timedelta(days=2))
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.NEEDS_HR)
        interview = Interview.objects.get()
        self.assertEqual(interview.status, InterviewStatus.NEEDS_HR_COORDINATION)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(CommunicationLog.objects.exists())
        self.assertTrue(CandidateEvent.objects.filter(candidate=self.candidate, event_type=EVENT.INTERVIEW_AUTO_SCHEDULE_FAILED).exists())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.INTERVIEW_PROPOSED)

    def test_hiring_manager_is_preferred_over_other_interviewers(self):
        other = User.objects.create_user("int2", "int2@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.free(other, "10:00", "12:00")
        self.free(self.manager, "11:00", "13:00")
        self.go(FakeLLM(stated(self.day)))
        self.assertEqual(Interview.objects.get().interviewer, self.manager)

    def test_other_interviewer_is_used_when_the_manager_has_no_overlap(self):
        other = User.objects.create_user("int2", "int2@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.free(self.manager, day=self.day + timedelta(days=3))
        self.free(other, "12:00", "13:00")
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.SCHEDULED)
        self.assertEqual(Interview.objects.get().interviewer, other)

    def test_booked_interviewer_slots_are_not_double_booked(self):
        self.free(self.manager, "11:00", "11:45")
        first = self.go(FakeLLM(stated(self.day)))
        self.assertEqual(first, AutoScheduleOutcome.SCHEDULED)
        second = Candidate.objects.create(
            requisition=self.requisition, full_name="Omar", email="omar@example.test",
            current_status=CandidateStatus.APPROVED_FOR_INTERVIEW, created_by=self.recruiter,
        )
        screening = Screening.objects.create(
            candidate=second, requisition=self.requisition, status=ScreeningStatus.REVIEWED, questions=["Q"],
            script_version="v", created_by=self.recruiter, candidate_stated_availability="same day",
            call_timestamp=timezone.now(),
        )
        ScreeningReview.objects.create(
            screening=screening, candidate=second, decision=ScreeningDecision.APPROVE_FOR_INTERVIEW,
            previous_candidate_status="X", resulting_candidate_status="Y", decided_by=self.recruiter,
        )
        with patch("scheduling.services.auto.get_llm_provider", return_value=FakeLLM(stated(self.day))):
            self.assertEqual(auto_schedule_candidate(second.pk), AutoScheduleOutcome.NEEDS_HR)
        self.assertEqual(len(mail.outbox), 1)

    def test_missing_availability_statement_goes_to_hr_without_calling_the_model(self):
        self.free(self.manager)
        Screening.objects.update(candidate_stated_availability="", availability_statement="")
        llm = FakeLLM(stated(self.day))
        self.assertEqual(self.go(llm), AutoScheduleOutcome.NEEDS_HR)
        self.assertEqual(llm.calls, [])
        self.assertFalse(Interview.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_model_failure_goes_to_hr_and_is_not_retried_by_the_sweep(self):
        self.free(self.manager)
        self.assertEqual(self.go(FakeLLM(error=RuntimeError("provider down"))), AutoScheduleOutcome.NEEDS_HR)
        self.assertFalse(Interview.objects.exists())
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(candidates_awaiting_auto_schedule().filter(pk=self.candidate.pk).exists())

    def test_invalid_dates_from_the_model_are_ignored(self):
        self.free(self.manager)
        past = (timezone.now().astimezone(PKT) - timedelta(days=5)).date()
        self.assertEqual(self.go(FakeLLM(stated(past))), AutoScheduleOutcome.NEEDS_HR)
        far = (timezone.now().astimezone(PKT) + timedelta(days=90)).date()
        self.assertEqual(self.go(FakeLLM(stated(far))), AutoScheduleOutcome.NEEDS_HR)
        bad = CandidateAvailabilityOut(timezone="Mars/Base", windows=[AvailabilityWindowOut(date="not-a-date", start_time="x", end_time="y")])
        self.assertEqual(self.go(FakeLLM(bad)), AutoScheduleOutcome.NEEDS_HR)
        self.assertEqual(len(mail.outbox), 0)

    def test_unknown_time_zone_falls_back_to_the_default(self):
        self.free(self.manager)
        out = stated(self.day, tz="Mars/Base")
        self.assertEqual(self.go(FakeLLM(out)), AutoScheduleOutcome.SCHEDULED)
        self.assertEqual(Interview.objects.get().timezone, "Asia/Karachi")

    def test_send_failure_keeps_the_draft_and_never_claims_the_interview_is_scheduled(self):
        self.free(self.manager)
        with patch("communications.services.EmailMessage.send", side_effect=OSError("smtp down")):
            self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.NEEDS_HR)
        interview = Interview.objects.get()
        self.assertEqual(interview.status, InterviewStatus.SLOT_CONFIRMED)
        log = CommunicationLog.objects.get()
        self.assertEqual(log.send_status, SendStatus.FAILED)
        self.candidate.refresh_from_db()
        self.assertNotEqual(self.candidate.current_status, CandidateStatus.INTERVIEW_SCHEDULED)
        self.assertEqual(len(mail.outbox), 0)

    def test_candidate_without_email_is_left_for_hr(self):
        self.free(self.manager)
        Candidate.objects.filter(pk=self.candidate.pk).update(email=None)
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.NEEDS_HR)
        self.assertFalse(Interview.objects.exists())

    def test_requisition_without_location_cannot_be_scheduled_on_site(self):
        self.free(self.manager)
        Requisition.objects.update(location="")
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.NEEDS_HR)
        self.assertFalse(Interview.objects.exists())

    def test_nothing_happens_when_disabled_or_candidate_not_approved(self):
        self.free(self.manager)
        with override_settings(INTERVIEW_AUTO_SCHEDULING_ENABLED=False):
            self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.SKIPPED)
        Candidate.objects.update(current_status=CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.SKIPPED)
        self.assertFalse(Interview.objects.exists())

    def test_safe_wrapper_records_unexpected_errors_for_hr(self):
        with patch("scheduling.services.auto.auto_schedule_candidate", side_effect=ValueError("boom")):
            self.assertEqual(safe_auto_schedule(self.candidate.pk), AutoScheduleOutcome.NEEDS_HR)
        self.assertTrue(CandidateEvent.objects.filter(candidate=self.candidate, event_type=EVENT.INTERVIEW_AUTO_SCHEDULE_FAILED).exists())

    def test_sweep_finds_only_candidates_never_attempted(self):
        self.assertTrue(candidates_awaiting_auto_schedule().filter(pk=self.candidate.pk).exists())
        CandidateEvent.objects.create(candidate=self.candidate, event_type=EVENT.INTERVIEW_AUTO_SCHEDULE_FAILED, details={})
        self.assertFalse(candidates_awaiting_auto_schedule().filter(pk=self.candidate.pk).exists())


@override_settings(EMAIL_BACKEND=LOCMEM, SCREENING_ORGANIZATION_NAME="Netsol", INTERVIEW_AUTO_SCHEDULING_ENABLED=True)
class AutoScheduleVideoTests(AutoFixture, TestCase):
    def setUp(self):
        self.make(interview_format=InterviewFormat.VIDEO, whatsapp="+923001234567")

    def test_video_format_emails_the_whatsapp_video_call_time_and_number(self):
        self.free(self.manager)
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.SCHEDULED)
        interview = Interview.objects.get()
        self.assertEqual(interview.mode, InterviewMode.VIDEO)
        self.assertEqual(interview.contact_whatsapp, "+923001234567")
        self.assertEqual(interview.meeting_link, "")
        body = mail.outbox[0].body
        self.assertIn("WhatsApp video call", body)
        self.assertIn("+923001234567", body)
        self.assertIn("11:00", body)
        self.assertNotIn("on-site", body)
        ics = mail.outbox[0].attachments[0][1]
        self.assertIn("WhatsApp video call +923001234567", ics)

    def test_video_requisition_without_a_number_is_left_for_hr(self):
        self.free(self.manager)
        Requisition.objects.update(interview_whatsapp_number="")
        self.assertEqual(self.go(FakeLLM(stated(self.day))), AutoScheduleOutcome.NEEDS_HR)
        self.assertFalse(Interview.objects.exists())


@override_settings(EMAIL_BACKEND=LOCMEM, INTERVIEW_AUTO_SCHEDULING_ENABLED=True)
class AutoScheduleTriggerAndApiTests(AutoFixture, APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.make()

    def test_approving_the_screening_queues_automatic_scheduling_after_commit(self):
        ScreeningReview.objects.all().delete()
        Candidate.objects.update(current_status=CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        Screening.objects.update(status=ScreeningStatus.AWAITING_HR_REVIEW)
        screening = Screening.objects.get()
        with patch("scheduling.tasks.queue_auto_scheduling") as queue:
            with self.captureOnCommitCallbacks(execute=True):
                review_screening(screening, self.recruiter, ScreeningDecision.APPROVE_FOR_INTERVIEW, "")
            queue.assert_called_once_with(self.candidate.pk)

    def test_declining_or_rescreening_does_not_queue_scheduling(self):
        ScreeningReview.objects.all().delete()
        Candidate.objects.update(current_status=CandidateStatus.SCREENING_COMPLETED_HR_REVIEW)
        Screening.objects.update(status=ScreeningStatus.AWAITING_HR_REVIEW)
        with patch("scheduling.tasks.queue_auto_scheduling") as queue:
            with self.captureOnCommitCallbacks(execute=True):
                review_screening(Screening.objects.get(), self.recruiter, ScreeningDecision.DECLINE, "Not a fit")
            queue.assert_not_called()

    def test_recruiter_can_rerun_the_agent_and_hiring_manager_cannot(self):
        self.free(self.manager)
        url = reverse("scheduling:candidate-interview-auto", args=[self.candidate.public_id])
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(url).status_code, 403)
        self.client.force_authenticate(self.recruiter)
        with patch("scheduling.services.auto.get_llm_provider", return_value=FakeLLM(stated(self.day))):
            response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["outcome"], AutoScheduleOutcome.SCHEDULED)
        self.assertTrue(response.data["interview"]["auto_scheduled"])
        self.assertEqual(self.client.post(url).data["outcome"], AutoScheduleOutcome.SKIPPED)
        self.assertEqual(len(mail.outbox), 1)
