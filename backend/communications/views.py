"""Candidate communications API: drafts, edits, explicit approval and sending (recruiters/admins)."""

from django.shortcuts import get_object_or_404
from rest_framework import exceptions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsHRStaff
from scheduling.models import Interview
from .models import CommunicationLog
from .serializers import ApproveSendSerializer, CommunicationLogSerializer, DraftUpdateSerializer
from .services import CommunicationError, approve_and_send, discard_draft, draft_message, update_draft


def _bad(exc):
    return exceptions.ValidationError({"detail": str(exc)})


def logs():
    return CommunicationLog.objects.select_related("candidate", "interview", "approved_by", "created_by")


class CommunicationListView(APIView):
    permission_classes = [IsHRStaff]

    def get(self, request):
        qs = logs()
        if request.query_params.get("candidate"):
            qs = qs.filter(candidate__public_id=request.query_params["candidate"])
        if request.query_params.get("interview"):
            qs = qs.filter(interview__public_id=request.query_params["interview"])
        if request.query_params.get("pending") == "1":
            qs = qs.filter(approval_status="DRAFT")
        return Response(CommunicationLogSerializer(qs[:200], many=True).data)


class InterviewDraftView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, interview_id):
        interview = get_object_or_404(Interview.objects.select_related("candidate", "requisition", "interviewer"), public_id=interview_id)
        try:
            log = draft_message(interview, request.user)
        except CommunicationError as exc:
            raise _bad(exc) from exc
        return Response(CommunicationLogSerializer(log).data, status=status.HTTP_201_CREATED)


class CommunicationDetailView(GenericAPIView):
    permission_classes = [IsHRStaff]
    serializer_class = DraftUpdateSerializer

    def get(self, request, public_id):
        return Response(CommunicationLogSerializer(get_object_or_404(logs(), public_id=public_id)).data)

    def patch(self, request, public_id):
        log = get_object_or_404(logs(), public_id=public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            log = update_draft(log, serializer.validated_data["subject"], serializer.validated_data["body"])
        except CommunicationError as exc:
            raise _bad(exc) from exc
        return Response(CommunicationLogSerializer(log).data)


class ApproveSendView(GenericAPIView):
    permission_classes = [IsHRStaff]
    serializer_class = ApproveSendSerializer

    def post(self, request, public_id):
        log = get_object_or_404(logs(), public_id=public_id)
        self.get_serializer(data=request.data).is_valid(raise_exception=True)
        try:
            log = approve_and_send(log, request.user)
        except CommunicationError as exc:
            log.refresh_from_db()
            raise exceptions.ValidationError({"detail": str(exc), "send_status": log.send_status}) from exc
        return Response(CommunicationLogSerializer(log).data)


class DiscardView(APIView):
    permission_classes = [IsHRStaff]

    def post(self, request, public_id):
        try:
            log = discard_draft(get_object_or_404(logs(), public_id=public_id), request.user)
        except CommunicationError as exc:
            raise _bad(exc) from exc
        return Response(CommunicationLogSerializer(log).data)
