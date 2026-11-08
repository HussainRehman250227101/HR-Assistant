from unittest.mock import Mock, patch

from django.test import TestCase

from accounts.models import User, UserRole
from candidates.models import Candidate, CandidateStatus, ResumeDocument, ResumeProcessingStatus
from requisitions.models import Requisition, RequisitionStatus
from .models import DEFAULT_SCORING_WEIGHTS, ConfidenceLevel, ResumeEvaluation, ScoringRubric
from .schemas import CriterionAssessment, ResumeScoringOutput
from .services.agent import (
    _calculate_weighted_score,
    _verify_evidence_excerpts,
    evaluate_candidate_resume,
)
from .services.rubrics import get_or_create_rubric


def scoring_result():
    def assessment(score, excerpt=None, evidence_status="SUPPORTED"):
        return {
            "evidence_status": evidence_status,
            "score": score,
            "rationale": "The resume provides role-related evidence.",
            "evidence": [
                {
                    "excerpt": excerpt,
                    "relevance": "Directly relevant to the criterion.",
                    "resume_section": "Experience",
                }
            ] if excerpt else [],
            "missing_or_unclear": [],
        }

    return ResumeScoringOutput.model_validate({
        "required_skills": assessment(90, "PLC and SCADA"),
        "relevant_experience": assessment(80, "Five years of controls engineering experience."),
        "role_related_projects": assessment(70, "Completed multiple industrial automation projects."),
        "education_certifications": assessment(None, evidence_status="NOT_FOUND"),
        "other_job_evidence": assessment(60, "using Allen-Bradley controls.", "PARTIAL"),
        "overall_assessment": "Evidence supports several role-related capabilities; education evidence is not present.",
        "additional_missing_or_unclear": [],
        "warnings": [],
    })


class ScoringCalculationTests(TestCase):
    def test_missing_evidence_is_excluded_from_weighted_denominator(self):
        overall, assessed, scores, evidence, missing, confidence = _calculate_weighted_score(
            scoring_result(), DEFAULT_SCORING_WEIGHTS
        )
        expected = round((90 * 40 + 80 * 25 + 70 * 20 + 60 * 5) / 90)
        self.assertEqual(overall, expected)
        self.assertEqual(assessed, 90)
        self.assertIsNone(scores["education_certifications"]["score"])
        self.assertIn(
            "Education and certifications: no evidence found in the supplied resume.",
            missing,
        )
        self.assertEqual(confidence, ConfidenceLevel.HIGH)

    def test_no_evidence_returns_no_score_not_a_zero_candidate_score(self):
        output = scoring_result()
        for key in DEFAULT_SCORING_WEIGHTS:
            setattr(output, key, CriterionAssessment(
                evidence_status="NOT_FOUND",
                score=None,
                rationale="No evidence was identified in the supplied text.",
            ))
        overall, assessed, *_ = _calculate_weighted_score(output, DEFAULT_SCORING_WEIGHTS)
        self.assertIsNone(overall)
        self.assertEqual(assessed, 0)

    def test_unverifiable_model_excerpt_is_discarded_and_marked_unclear(self):
        output = scoring_result()
        payload = output.model_dump()
        payload["required_skills"]["evidence"][0]["excerpt"] = "Invented skill claim not in resume"
        checked = _verify_evidence_excerpts(
            ResumeScoringOutput.model_validate(payload),
            "The original resume contains PLC and SCADA.",
        )
        self.assertEqual(checked.required_skills.evidence_status, "UNCLEAR")
        self.assertIsNone(checked.required_skills.score)
        self.assertEqual(checked.required_skills.evidence, [])
        self.assertTrue(checked.warnings)


class ScoringServiceTests(TestCase):
    def setUp(self):
        self.recruiter = User.objects.create_user(
            username="score-recruiter", email="score@example.test",
            password="Strong-Test-Password-123!", role=UserRole.ADMIN,
        )
        self.requisition = Requisition.objects.create(
            title="Controls Engineer", department="Engineering",
            description="PLC and SCADA engineering.",
            responsibilities="Design and test control systems.",
            required_skills=["PLC", "SCADA"],
            minimum_experience_years="3.0",
            status=RequisitionStatus.OPEN, created_by=self.recruiter,
        )
        self.candidate = Candidate.objects.create(
            requisition=self.requisition, full_name="Synthetic Candidate",
            email="synthetic@example.test", created_by=self.recruiter,
        )
        self.document = ResumeDocument.objects.create(
            candidate=self.candidate, file="resumes/test.docx",
            original_filename="test.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            file_size=100, sha256="a" * 64,
            processing_status=ResumeProcessingStatus.COMPLETED,
            extracted_text=(
                "PLC and SCADA. Five years of controls engineering experience. "
                "Completed multiple industrial automation projects. using Allen-Bradley controls."
            ),
            created_by=self.recruiter,
        )

    @patch("scoring.services.agent.get_llm_provider")
    def test_scoring_saves_weighted_evaluation_and_moves_candidate_to_hr_review(self, get_provider):
        provider = Mock()
        provider.deployment_name = "hr-gpt-5-mini"
        provider.generate_structured.return_value = scoring_result()
        get_provider.return_value = provider

        evaluation = evaluate_candidate_resume(
            candidate_id=self.candidate.pk,
            resume_document_id=self.document.public_id,
            actor=self.recruiter,
        )
        self.candidate.refresh_from_db()
        self.assertIsNotNone(evaluation.overall_score)
        self.assertEqual(evaluation.assessed_weight, 90)
        self.assertEqual(evaluation.model_version, "hr-gpt-5-mini")
        self.assertEqual(evaluation.version, 1)
        self.assertEqual(self.candidate.current_status, CandidateStatus.SCORED_HR_REVIEW)
        self.assertEqual(ResumeEvaluation.objects.count(), 1)
        messages = provider.generate_structured.call_args.kwargs["messages"]
        self.assertNotIn("Synthetic Candidate", messages[1]["content"])
        self.assertNotIn("synthetic@example.test", messages[1]["content"])

    @patch("scoring.services.agent.get_llm_provider")
    def test_manual_review_is_required_for_low_evidence_coverage(self, get_provider):
        output = scoring_result()
        for key in ("required_skills", "relevant_experience", "role_related_projects"):
            setattr(output, key, CriterionAssessment(
                evidence_status="NOT_FOUND",
                score=None,
                rationale="No evidence found.",
            ))
        provider = Mock()
        provider.deployment_name = "hr-gpt-5-mini"
        provider.generate_structured.return_value = output
        get_provider.return_value = provider
        evaluation = evaluate_candidate_resume(self.candidate.pk, actor=self.recruiter)
        self.candidate.refresh_from_db()
        self.assertEqual(evaluation.recommendation_for_human_review, "MANUAL_REVIEW_REQUIRED")
        self.assertEqual(self.candidate.current_status, CandidateStatus.NEEDS_MANUAL_REVIEW)

    def test_scoring_requires_a_completed_resume(self):
        self.document.processing_status = ResumeProcessingStatus.PENDING
        self.document.save(update_fields=("processing_status",))
        with self.assertRaisesMessage(ValueError, "No successfully processed resume"):
            evaluate_candidate_resume(self.candidate.pk, actor=self.recruiter)

    def test_rubric_versions_are_immutable_and_historical_evaluations_keep_old_version(self):
        original = get_or_create_rubric(self.requisition)
        provider = Mock()
        provider.deployment_name = "hr-gpt-5-mini"
        provider.generate_structured.return_value = scoring_result()
        with patch("scoring.services.agent.get_llm_provider", return_value=provider):
            evaluation = evaluate_candidate_resume(self.candidate.pk, actor=self.recruiter)
        original_weights = original.weights.copy()
        from scoring.views import RequisitionRubricView
        from rest_framework.test import APIRequestFactory, force_authenticate
        factory = APIRequestFactory()
        request = factory.put(
            f"/api/v1/scoring/requisitions/{self.requisition.reference_code}/rubric/",
            {
                "name": "Rebalanced rubric",
                "weights": {
                    "required_skills": 35,
                    "relevant_experience": 25,
                    "role_related_projects": 20,
                    "education_certifications": 15,
                    "other_job_evidence": 5,
                },
                "notes": "Rebalanced for this role.",
            },
            format="json",
        )
        force_authenticate(request, user=self.recruiter)
        response = RequisitionRubricView.as_view()(request, reference_code=self.requisition.reference_code)
        self.assertEqual(response.status_code, 200)
        evaluation.refresh_from_db()
        original.refresh_from_db()
        self.assertFalse(original.is_active)
        self.assertEqual(evaluation.rubric_id, original.pk)
        self.assertEqual(evaluation.rubric.weights, original_weights)
        self.assertEqual(response.data["version"], 2)
