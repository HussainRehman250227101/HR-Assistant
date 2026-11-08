"""Serializer-backed scoring endpoints for the DRF Browsable API."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from accounts.permissions import IsHRStaff
from audit.models import log_audit
from candidates.models import Candidate
from llm.exceptions import LLMConfigurationError, LLMProviderError
from requisitions.models import Requisition
from .models import ScoringRubric
from .serializers import (
    EvaluationDetailSerializer,
    EvaluationListSerializer,
    EvaluationRequestSerializer,
    ScoringRubricSerializer,
)
from .services.agent import evaluate_candidate_resume
from .services.rubrics import get_or_create_rubric


class RequisitionRubricView(GenericAPIView):
    permission_classes = [IsHRStaff]
    serializer_class = ScoringRubricSerializer

    def get(self, request, reference_code):
        requisition = get_object_or_404(Requisition, reference_code=reference_code)
        rubric = get_or_create_rubric(requisition)
        return Response(ScoringRubricSerializer(rubric).data)

    def put(self, request, reference_code):
        requisition = get_object_or_404(Requisition, reference_code=reference_code)
        current = get_or_create_rubric(requisition)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            current.is_active = False
            current.save(update_fields=("is_active", "updated_at"))
            rubric = ScoringRubric.objects.create(
                requisition=requisition,
                name=data.get("name", current.name),
                weights=data["weights"],
                version=current.version + 1,
                is_active=True,
                notes=data.get("notes", ""),
                updated_by=request.user,
            )
            log_audit(request.user, "RUBRIC_VERSION_CREATED", "requisition", requisition.reference_code,
                      version=rubric.version, previous_weights=current.weights, weights=rubric.weights,
                      notes=rubric.notes)
        return Response(ScoringRubricSerializer(rubric).data)


class CandidateEvaluationView(GenericAPIView):
    permission_classes = [IsHRStaff]
    serializer_class = EvaluationRequestSerializer

    def post(self, request, candidate_id):
        candidate = get_object_or_404(Candidate, public_id=candidate_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            evaluation = evaluate_candidate_resume(
                candidate_id=candidate.pk,
                resume_document_id=serializer.validated_data.get("resume_document"),
                actor=request.user,
            )
        except ValueError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        except (LLMConfigurationError, LLMProviderError) as exc:
            raise exceptions.APIException(
                "The scoring provider could not complete this evaluation. Check Azure configuration and retry later."
            ) from exc
        return Response(EvaluationDetailSerializer(evaluation).data, status=status.HTTP_201_CREATED)


class CandidateEvaluationHistoryView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, candidate_id):
        candidate = get_object_or_404(Candidate, public_id=candidate_id)
        user = request.user
        allowed = (
            user.is_superuser
            or getattr(user, "role", None) in ("ADMIN", "RECRUITER")
            or (
                getattr(user, "role", None) == "HIRING_MANAGER"
                and candidate.requisition.hiring_manager_id == user.pk
            )
        )
        if not allowed:
            raise exceptions.PermissionDenied("You cannot access this candidate's evaluations.")
        evaluations = candidate.resume_evaluations.select_related("rubric").all()
        return Response(EvaluationListSerializer(evaluations, many=True).data)


class EvaluationDetailView(GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, public_id):
        from .models import ResumeEvaluation

        evaluation = get_object_or_404(
            ResumeEvaluation.objects.select_related("candidate", "requisition", "resume_document", "rubric"),
            public_id=public_id,
        )
        user = request.user
        allowed = (
            user.is_superuser
            or getattr(user, "role", None) in ("ADMIN", "RECRUITER")
            or (
                getattr(user, "role", None) == "HIRING_MANAGER"
                and evaluation.requisition.hiring_manager_id == user.pk
            )
        )
        if not allowed:
            raise exceptions.PermissionDenied("You cannot access this evaluation.")
        return Response(EvaluationDetailSerializer(evaluation).data)
