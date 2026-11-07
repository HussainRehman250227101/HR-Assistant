"""Scheduling API. Recruiters/admins manage interviews; interviewers maintain their own availability."""

from datetime import timedelta

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import UserRole
from accounts.permissions import IsRecruiterOrAdmin
from candidates.views import candidates_visible_to
from .models import ACTIVE_INTERVIEW_STATUSES, AvailabilitySlot, Interview
from .serializers import (
    AvailabilityCreateSerializer, AvailabilitySlotSerializer, CancelSerializer, ConfirmSlotSerializer,
    InterviewPlanSerializer, InterviewReproposeSerializer, InterviewSerializer,
)
from .services.interviews import cancel_interview, confirm_slot, plan_interview, repropose
from .services.slots import SchedulingError, local_window_to_utc


def is_recruiter(user):
    return user.is_superuser or getattr(user, "role", None) in (UserRole.ADMIN, UserRole.RECRUITER)


def interviews_visible_to(user):
    qs = Interview.objects.select_related("candidate", "requisition", "interviewer", "created_by")
    if is_recruiter(user):
        return qs
    return qs.filter(Q(candidate__in=candidates_visible_to(user)) | Q(interviewer=user))


def _bad(exc):
    return exceptions.ValidationError({"detail": str(exc)})


class AvailabilityListView(GenericAPIView):
    serializer_class = AvailabilityCreateSerializer

    def get(self, request):
        qs = AvailabilitySlot.objects.select_related("interviewer").filter(end__gte=timezone.now() - timedelta(days=1))
        interviewer = request.query_params.get("interviewer")
        if not is_recruiter(request.user):
            qs = qs.filter(interviewer=request.user)
        elif interviewer:
            qs = qs.filter(interviewer_id=interviewer)
        return Response(AvailabilitySlotSerializer(qs[:500], many=True).data)

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        interviewer = data.get("interviewer") or request.user
        if interviewer != request.user and not is_recruiter(request.user):
            raise exceptions.PermissionDenied("You can only manage your own availability.")
        try:
            start, end = local_window_to_utc(data["date"], data["start_time"], data["end_time"], data["timezone"])
        except SchedulingError as exc:
            raise _bad(exc) from exc
        if end <= timezone.now():
            raise exceptions.ValidationError({"detail": "Availability must be in the future."})
        if AvailabilitySlot.objects.filter(interviewer=interviewer, start__lt=end, end__gt=start).exists():
            raise exceptions.ValidationError({"detail": "This window overlaps existing availability."})
        slot = AvailabilitySlot.objects.create(interviewer=interviewer, start=start, end=end,
                                               timezone=data["timezone"], created_by=request.user)
        return Response(AvailabilitySlotSerializer(slot).data, status=status.HTTP_201_CREATED)


class AvailabilityDetailView(APIView):
    def delete(self, request, public_id):
        slot = get_object_or_404(AvailabilitySlot, public_id=public_id)
        if slot.interviewer != request.user and not is_recruiter(request.user):
            raise exceptions.PermissionDenied("You can only manage your own availability.")
        slot.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class InterviewListView(APIView):
    def get(self, request):
        qs = interviews_visible_to(request.user)
        status_filter = request.query_params.get("status")
        if status_filter == "ACTIVE":
            qs = qs.filter(status__in=ACTIVE_INTERVIEW_STATUSES)
        elif status_filter:
            qs = qs.filter(status=status_filter)
        if request.query_params.get("mine") == "1":
            qs = qs.filter(interviewer=request.user)
        return Response(InterviewSerializer(qs.order_by("confirmed_start", "-updated_at")[:200], many=True).data)


class CandidateInterviewView(GenericAPIView):
    serializer_class = InterviewPlanSerializer

    def get_permissions(self):
        return [IsRecruiterOrAdmin()] if self.request.method == "POST" else [permissions.IsAuthenticated()]

    def get(self, request, candidate_id):
        candidate = get_object_or_404(candidates_visible_to(request.user), public_id=candidate_id)
        return Response(InterviewSerializer(interviews_visible_to(request.user).filter(candidate=candidate), many=True).data)

    def post(self, request, candidate_id):
        candidate = get_object_or_404(candidates_visible_to(request.user).select_related("requisition"), public_id=candidate_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = plan_interview(candidate, request.user, serializer.validated_data)
        except SchedulingError as exc:
            raise _bad(exc) from exc
        return Response(InterviewSerializer(interview).data, status=status.HTTP_201_CREATED)


class InterviewDetailView(APIView):
    def get(self, request, public_id):
        return Response(InterviewSerializer(get_object_or_404(interviews_visible_to(request.user), public_id=public_id)).data)


class _InterviewAction(GenericAPIView):
    permission_classes = [IsRecruiterOrAdmin]

    def get_interview(self, public_id):
        return get_object_or_404(interviews_visible_to(self.request.user), public_id=public_id)


class InterviewReproposeView(_InterviewAction):
    serializer_class = InterviewReproposeSerializer

    def post(self, request, public_id):
        interview = self.get_interview(public_id)
        serializer = self.get_serializer(data=request.data, context={"interview": interview, "request": request})
        serializer.is_valid(raise_exception=True)
        try:
            interview = repropose(interview, request.user, serializer.validated_data)
        except SchedulingError as exc:
            raise _bad(exc) from exc
        return Response(InterviewSerializer(interview).data)


class InterviewConfirmSlotView(_InterviewAction):
    serializer_class = ConfirmSlotSerializer

    def post(self, request, public_id):
        interview = self.get_interview(public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            interview = confirm_slot(interview, request.user, data["slot_start"], data["candidate_confirmed"], data["interviewer_confirmed"])
        except SchedulingError as exc:
            raise _bad(exc) from exc
        return Response(InterviewSerializer(interview).data)


class InterviewCancelView(_InterviewAction):
    serializer_class = CancelSerializer

    def post(self, request, public_id):
        interview = self.get_interview(public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            interview = cancel_interview(interview, request.user, serializer.validated_data["reason"])
        except SchedulingError as exc:
            raise _bad(exc) from exc
        return Response(InterviewSerializer(interview).data)
