"""The assigned interviewer marks an interview done and rates every question the administrator set."""

from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import User, UserRole
from candidates.models import CandidateEvent, CandidateStatus
from .models import Interview, InterviewFeedback, InterviewStatus
from .tests import Fixture


@override_settings(INTERVIEW_TESTING_MODE=False)  # a developer .env may switch the testing mode on
class InterviewFeedbackTests(Fixture, APITestCase):
    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.make()  # self.recruiter = ADMIN, self.manager = RECRUITER (the interviewer)
        self.requisition.interview_questions = ["Technical depth?", "Communication?", "Culture fit?"]
        self.requisition.save()
        start = timezone.now() - timedelta(hours=2)
        self.interview = Interview.objects.create(
            candidate=self.candidate, requisition=self.requisition, interviewer=self.manager, timezone="UTC",
            status=InterviewStatus.SCHEDULED, confirmed_start=start, confirmed_end=start + timedelta(hours=1),
            created_by=self.recruiter,
        )
        self.url = reverse("scheduling:interview-complete", args=[self.interview.public_id])
        self.answers = [{"index": 0, "rating": "GOOD"}, {"index": 1, "rating": "AVERAGE"}, {"index": 2, "rating": "GOOD"}]
        self.client.force_authenticate(self.manager)

    def test_interviewer_completes_with_all_answers_and_admin_sees_the_outcome(self):
        r = self.client.post(self.url, {"answers": self.answers, "comment": "Strong candidate."}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "COMPLETED")
        self.assertEqual(r.data["feedback"]["overall_rating"], "GOOD")  # (3 + 2 + 3) / 3 = 2.67
        self.assertEqual([a["rating"] for a in r.data["feedback"]["answers"]], ["GOOD", "AVERAGE", "GOOD"])
        self.assertEqual(r.data["feedback"]["answers"][0]["question"], "Technical depth?")
        self.assertTrue(CandidateEvent.objects.filter(event_type=CandidateEvent.EventType.INTERVIEW_COMPLETED).exists())
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.APPROVED_FOR_INTERVIEW)  # unchanged: no automatic decision
        self.client.force_authenticate(self.recruiter)
        seen = self.client.get(reverse("scheduling:interview-detail", args=[self.interview.public_id]))
        self.assertEqual(seen.data["feedback"]["comment"], "Strong candidate.")

    def test_every_question_must_be_answered_exactly_once(self):
        for bad in (self.answers[:2], self.answers + [{"index": 1, "rating": "POOR"}], [{"index": 5, "rating": "GOOD"}] + self.answers[:2]):
            r = self.client.post(self.url, {"answers": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
        self.assertEqual(self.client.post(self.url, {"answers": [{"index": 0, "rating": "EXCELLENT"}] + self.answers[1:]}, format="json").status_code, 400)
        self.assertFalse(InterviewFeedback.objects.exists())

    def test_only_the_assigned_interviewer_and_only_once(self):
        other = User.objects.create_user("o", "o@example.test", "Pass-12345!", role=UserRole.RECRUITER)
        self.client.force_authenticate(other)
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 404)  # not visible to them
        self.client.force_authenticate(self.recruiter)
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 400)  # admin is not the interviewer
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 400)
        self.assertEqual(InterviewFeedback.objects.count(), 1)

    def test_cannot_complete_before_the_interview_starts(self):
        Interview.objects.filter(pk=self.interview.pk).update(confirmed_start=timezone.now() + timedelta(days=1))
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 400)

    def test_requisition_without_questions_only_needs_the_click(self):
        self.requisition.interview_questions = []
        self.requisition.save()
        r = self.client.post(self.url, {}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["feedback"]["overall_rating"], "")

    def test_completed_interview_cannot_be_cancelled_and_frees_the_candidate(self):
        self.client.post(self.url, {"answers": self.answers}, format="json")
        self.client.force_authenticate(self.recruiter)
        cancel = self.client.post(reverse("scheduling:interview-cancel", args=[self.interview.public_id]), {"reason": "x"}, format="json")
        self.assertEqual(cancel.status_code, 400)
        self.assertFalse(Interview.objects.filter(candidate=self.candidate, status__in=("PROPOSED", "SLOT_CONFIRMED", "SCHEDULED")).exists())



@override_settings(INTERVIEW_TESTING_MODE=True)
class TestingModeFeedbackTests(InterviewFeedbackTests):
    """With the testing switch on, the flow can be tried before the interview starts and by HR/admin too.

    Subclassing re-runs every normal test too, so only the ones that differ are overridden below.
    """

    def test_every_question_must_be_answered_exactly_once(self):
        super().test_every_question_must_be_answered_exactly_once()  # answers are still mandatory in testing mode

    def test_only_the_assigned_interviewer_and_only_once(self):
        self.client.force_authenticate(self.recruiter)  # the admin may complete it in testing mode
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 200)
        self.assertEqual(self.client.post(self.url, {"answers": self.answers}, format="json").status_code, 400)  # still only once
        self.assertEqual(InterviewFeedback.objects.count(), 1)

    def test_cannot_complete_before_the_interview_starts(self):
        Interview.objects.filter(pk=self.interview.pk).update(confirmed_start=timezone.now() + timedelta(days=1))
        r = self.client.post(self.url, {"answers": self.answers}, format="json")
        self.assertEqual(r.status_code, 200, r.data)  # allowed in testing mode
        self.assertTrue(r.data["early_completion_allowed"])

