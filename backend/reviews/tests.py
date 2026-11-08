from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from requisitions.models import Requisition, RequisitionStatus
from scoring.models import ConfidenceLevel, EvaluationRecommendation, ResumeEvaluation, ScoringRubric
from .models import ShortlistDecision, ShortlistReview


class ShortlistReviewTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(
            username="review-recruiter", email="review@example.test",
            password="Strong-Test-Password-123!", role=UserRole.ADMIN,
        )
        self.manager = User.objects.create_user(
            username="review-manager", email="manager-review@example.test",
            password="Strong-Test-Password-123!", role=UserRole.HIRING_MANAGER,
        )
        self.requisition = Requisition.objects.create(
            title="Controls Engineer", department="Engineering",
            description="Controls role.", status=RequisitionStatus.OPEN,
            created_by=self.recruiter, hiring_manager=self.manager,
        )
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Review Candidate",
            email="review-candidate@example.test", created_by=self.recruiter,
            current_status=CandidateStatus.SCORED_HR_REVIEW,
        )
        self.rubric = ScoringRubric.objects.create(requisition=self.requisition)
        self.evaluation = self._make_evaluation(self.candidate, "c" * 64, 82)
        self.client = APIClient()
        self.client.force_authenticate(user=self.recruiter)
        self.url = reverse("reviews:candidate-shortlist-decision", args=[self.candidate.public_id])

    def _make_evaluation(self, candidate, checksum, score):
        document = ResumeDocument.objects.create(
            candidate=candidate, file=f"resumes/{checksum[:4]}.docx",
            original_filename="review.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=50, sha256=checksum, processing_status=ResumeProcessingStatus.COMPLETED,
            extracted_text="Synthetic resume evidence.", created_by=self.recruiter,
        )
        return ResumeEvaluation.objects.create(
            candidate=candidate, requisition=self.requisition,
            resume_document=document, rubric=self.rubric, version=1,
            overall_score=score, assessed_weight=100, criterion_scores={},
            evidence={}, missing_or_unclear_items=[], parsing_warnings=[],
            confidence_level=ConfidenceLevel.HIGH,
            recommendation_for_human_review=EvaluationRecommendation.REVIEW_RECOMMENDED,
            overall_assessment="Evidence summary.", model_version="hr-gpt-5-mini",
            input_sha256=checksum, created_by=self.recruiter,
        )

    def test_recruiter_approval_advances_candidate_only_after_human_decision(self):
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.APPROVE_FOR_SCREENING,
            "decision_reason": "Recruiter reviewed supporting evidence.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.APPROVED_FOR_SCREENING)
        self.assertEqual(ShortlistReview.objects.count(), 1)

    def test_decline_marks_the_candidate_and_queues_the_rejection_notice_after_the_decision(self):
        from unittest.mock import patch
        from candidates.models import CandidateEvent

        with patch("reviews.views.queue_declined_processing") as queue:
            response = self.client.post(self.url, {
                "evaluation": str(self.evaluation.public_id), "decision": ShortlistDecision.DECLINE,
                "decision_reason": "Missing required experience.",
            }, format="json")
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            queue.assert_called_once_with(self.candidate.pk)
        self.assertTrue(CandidateEvent.objects.filter(
            candidate=self.candidate, event_type=CandidateEvent.EventType.REJECTION_PENDING).exists())

    def test_approval_does_not_queue_a_rejection_notice(self):
        from unittest.mock import patch

        with patch("reviews.views.queue_declined_processing") as queue:
            self.client.post(self.url, {
                "evaluation": str(self.evaluation.public_id), "decision": ShortlistDecision.APPROVE_FOR_SCREENING,
                "decision_reason": "",
            }, format="json")
            queue.assert_not_called()

    def test_decline_requires_reason_and_closes_candidate(self):
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.DECLINE, "decision_reason": "",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.DECLINE,
            "decision_reason": "Recruiter decision after review.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.CLOSED)
        self.assertEqual(self.candidate.closed_reason, "Recruiter decision after review.")

    def test_manual_score_override_requires_reason_and_preserves_ai_score(self):
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.HOLD_FOR_REVIEW,
            "decision_reason": "Need a second reviewer.",
            "score_override": 90,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.HOLD_FOR_REVIEW,
            "decision_reason": "Need a second reviewer.",
            "score_override": 90,
            "score_override_reason": "Manual evidence review changed the internal priority.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.evaluation.refresh_from_db()
        self.assertEqual(self.evaluation.overall_score, 82)
        self.assertEqual(ShortlistReview.objects.get().score_override, 90)

    def test_evaluation_from_another_candidate_is_rejected(self):
        other = Candidate.objects.create(
            requisition=self.requisition, full_name="Other",
            email="other-review@example.test", created_by=self.recruiter,
        )
        other_evaluation = self._make_evaluation(other, "d" * 64, 70)
        response = self.client.post(self.url, {
            "evaluation": str(other_evaluation.public_id),
            "decision": ShortlistDecision.APPROVE_FOR_SCREENING,
            "decision_reason": "Approve.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.candidate.refresh_from_db()
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCORED_HR_REVIEW)

    def test_recruiter_interviewer_cannot_make_shortlist_decision(self):
        interviewer = User.objects.create_user(
            username="review-interviewer", email="interviewer-review@example.test",
            password="Strong-Test-Password-123!", role=UserRole.RECRUITER,
        )
        self.client.force_authenticate(user=interviewer)
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.APPROVE_FOR_SCREENING,
            "decision_reason": "Approve.",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_approval_is_refused_when_the_resume_had_no_contact_details(self):
        self.candidate.identity_review_required = True
        self.candidate.full_name = ""
        self.candidate.email = None
        self.candidate.phone = ""
        self.candidate.save()
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.APPROVE_FOR_SCREENING,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("candidate_details", response.data)

    def test_one_click_approval_confirms_details_read_from_the_resume(self):
        # Batch-uploaded candidate whose details were filled from the resume: no reason, no checkbox, no typing.
        self.candidate.identity_review_required = True
        self.candidate.full_name = "Resume Candidate"
        self.candidate.phone = "+923001234567"
        self.candidate.auto_filled_fields = ["full_name", "phone"]
        self.candidate.save()
        response = self.client.post(self.url, {
            "evaluation": str(self.evaluation.public_id),
            "decision": ShortlistDecision.APPROVE_FOR_SCREENING,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.candidate.refresh_from_db()
        self.assertFalse(self.candidate.identity_review_required)
        self.assertEqual(self.candidate.current_status, CandidateStatus.APPROVED_FOR_SCREENING)
        self.assertEqual(ShortlistReview.objects.get().decided_by, self.recruiter)
        event = self.candidate.events.get(event_type="CANDIDATE_IDENTITY_REVIEWED")
        self.assertEqual(event.details["fields_from_resume"], ["full_name", "phone"])
