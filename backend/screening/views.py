"""Screening call API. Recruiters/admins act; hiring managers read summaries for their requisitions."""

import json
import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from rest_framework import exceptions, permissions, status
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsHRAdmin, IsHRStaff, has_full_access
from candidates.views import candidates_visible_to
from . import script
from .models import ACTIVE_SCREENING_STATUSES, CallAttemptStatus, Screening, ScreeningCallAttempt, ScreeningStatus
from .serializers import (
    BrowserSessionCompleteSerializer, BrowserSessionStartSerializer, ManualResultSerializer, ReasonSerializer,
    ScreeningCallAttemptSerializer, ScreeningCreateSerializer, ScreeningReviewRequestSerializer, ScreeningSerializer,
)
from .services.browser import SessionState, complete_browser_session, start_browser_session
from .services.review import review_screening
from .services.calls import (
    ScreeningError, cancel_screening, create_screening, place_call, record_manual_result,
    retry_analysis, sync_screening, sync_attempt,
)
from .services.voice import VoiceConfigurationError, VoiceProviderError, configuration_status, verify_elevenlabs_signature

logger = logging.getLogger(__name__)


class VoiceNotConfigured(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The voice provider is not configured on the server."
    default_code = "voice_not_configured"


class VoiceProviderUnavailable(exceptions.APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "The voice provider could not complete the request. Try again shortly."
    default_code = "voice_provider_error"


is_recruiter = has_full_access  # historic name: HR Administrator / Hiring Manager see raw transcripts


def screenings_visible_to(user):
    return Screening.objects.select_related(
        "candidate", "requisition", "created_by", "result_recorded_by"
    ).prefetch_related("call_attempts__initiated_by").filter(candidate__in=candidates_visible_to(user))


def serialize(screening, user):
    data = ScreeningSerializer(screening).data
    if not is_recruiter(user):
        data["transcript"] = []  # least privilege: interviewers see the summary, not the raw transcript
    return data


def _voice_error(exc):
    if isinstance(exc, VoiceConfigurationError):
        return exceptions.APIException(str(exc))
    return exceptions.APIException("The call provider could not start the call. The failed attempt was recorded; retry later.")


class CandidateScreeningListView(GenericAPIView):
    serializer_class = ScreeningCreateSerializer

    def get_permissions(self):
        return [IsHRStaff()] if self.request.method == "POST" else [permissions.IsAuthenticated()]

    def get(self, request, candidate_id):
        candidate = get_object_or_404(candidates_visible_to(request.user), public_id=candidate_id)
        return Response([serialize(s, request.user) for s in screenings_visible_to(request.user).filter(candidate=candidate)])

    def post(self, request, candidate_id):
        candidate = get_object_or_404(candidates_visible_to(request.user).select_related("requisition"), public_id=candidate_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            screening = create_screening(candidate, request.user, serializer.validated_data["channel"])
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        call_error = None
        if serializer.validated_data["start_call_now"] and screening.channel == "AI_VOICE":
            try:
                place_call(screening, request.user)
            except ScreeningError as exc:
                call_error = str(exc)
            except (VoiceConfigurationError, VoiceProviderError) as exc:
                call_error = str(_voice_error(exc).detail)
            screening.refresh_from_db()
        data = serialize(screening, request.user)
        data["call_error"] = call_error
        return Response(data, status=status.HTTP_201_CREATED)


class ScreeningDetailView(APIView):
    def get(self, request, public_id):
        return Response(serialize(get_object_or_404(screenings_visible_to(request.user), public_id=public_id), request.user))


class ScreeningQueueView(APIView):
    """Screenings needing recruiter attention (pending calls, failures, results awaiting review)."""

    permission_classes = [IsHRStaff]

    def get(self, request):
        qs = screenings_visible_to(request.user).filter(status__in=ACTIVE_SCREENING_STATUSES)
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        requisition = request.query_params.get("requisition")
        if requisition:
            qs = qs.filter(requisition__reference_code=requisition)
        return Response([serialize(s, request.user) for s in qs.order_by("-updated_at")])


class _ScreeningAction(GenericAPIView):
    permission_classes = [IsHRStaff]

    def get_screening(self, public_id):
        return get_object_or_404(screenings_visible_to(self.request.user), public_id=public_id)


class ScreeningPlaceCallView(_ScreeningAction):
    def post(self, request, public_id):
        screening = self.get_screening(public_id)
        try:
            place_call(screening, request.user)
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        except (VoiceConfigurationError, VoiceProviderError) as exc:
            raise _voice_error(exc) from exc
        screening.refresh_from_db()
        return Response(serialize(screening, request.user), status=status.HTTP_202_ACCEPTED)


class ScreeningSyncView(_ScreeningAction):
    def post(self, request, public_id):
        screening = self.get_screening(public_id)
        try:
            screening = sync_screening(screening)
        except (VoiceConfigurationError, VoiceProviderError) as exc:
            raise exceptions.APIException("Call status could not be retrieved from the provider. Retry later.") from exc
        return Response(serialize(screening, request.user))


class ScreeningRetryAnalysisView(_ScreeningAction):
    def post(self, request, public_id):
        try:
            screening = retry_analysis(self.get_screening(public_id), request.user)
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        return Response(serialize(screening, request.user))


class ScreeningManualResultView(_ScreeningAction):
    serializer_class = ManualResultSerializer

    def post(self, request, public_id):
        screening = self.get_screening(public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            screening = record_manual_result(screening, request.user, serializer.validated_data)
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        return Response(serialize(screening, request.user))


class ScreeningCancelView(_ScreeningAction):
    serializer_class = ReasonSerializer

    def post(self, request, public_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            screening = cancel_screening(self.get_screening(public_id), request.user, serializer.validated_data["reason"])
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        return Response(serialize(screening, request.user))


class ScreeningReviewView(_ScreeningAction):
    """HR decision on a completed screening. Only a human can progress, re-screen or decline."""

    serializer_class = ScreeningReviewRequestSerializer

    def post(self, request, public_id):
        screening = self.get_screening(public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            review_screening(screening, request.user, serializer.validated_data["decision"],
                             serializer.validated_data.get("decision_reason", ""))
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        screening.refresh_from_db()
        return Response(serialize(screening, request.user), status=status.HTTP_201_CREATED)


class ScreeningBrowserSessionStartView(_ScreeningAction):
    """Start a browser voice session (no phone call): returns a short-lived ElevenLabs WebRTC conversation token."""

    serializer_class = BrowserSessionStartSerializer

    def post(self, request, public_id):
        screening = self.get_screening(public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = start_browser_session(screening, request.user, serializer.validated_data["consent_acknowledged"])
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        except VoiceConfigurationError as exc:
            raise VoiceNotConfigured(str(exc)) from exc
        except VoiceProviderError as exc:
            raise VoiceProviderUnavailable(
                f"ElevenLabs could not start the session: {exc} The failed attempt was recorded. "
                "Check the ElevenLabs API key and agent ID, then try again."
            ) from exc
        attempt = session["attempt"]
        response = Response({
            "screening_id": str(screening.public_id),
            "attempt_id": str(attempt.public_id),
            "attempt_number": attempt.attempt_number,
            "max_attempts": screening.max_attempts,
            "conversation_id": attempt.provider_conversation_id,
            "conversation_token": session["conversation_token"],
            "connection_type": "webrtc",
            "dynamic_variables": session["dynamic_variables"],
        }, status=status.HTTP_201_CREATED)
        response["Cache-Control"] = "no-store"
        return response


class ScreeningBrowserSessionCompleteView(_ScreeningAction):
    """Browser reports that the session ended; the backend fetches the authoritative result from ElevenLabs.

    202 + `session_state=processing` means ElevenLabs is still finalising the transcript; call again shortly.
    Repeated calls are safe: a concluded session is never concluded twice.
    """

    serializer_class = BrowserSessionCompleteSerializer

    def post(self, request, public_id):
        screening = self.get_screening(public_id)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            attempt, state = complete_browser_session(
                screening, request.user, attempt_id=data.get("attempt_id"),
                client_end_reason=data["client_end_reason"], connected=data["connected"],
                client_conversation_id=data.get("conversation_id") or None,
            )
        except ScreeningError as exc:
            raise exceptions.ValidationError({"detail": str(exc)}) from exc
        except VoiceConfigurationError as exc:
            raise VoiceNotConfigured(str(exc)) from exc
        except VoiceProviderError as exc:
            raise VoiceProviderUnavailable(
                "The session result could not be retrieved from ElevenLabs. Nothing was lost; try again shortly."
            ) from exc
        payload = serialize(screening, request.user)
        payload["session_state"] = state
        payload["session_attempt"] = ScreeningCallAttemptSerializer(attempt).data
        return Response(payload, status=status.HTTP_202_ACCEPTED if state == SessionState.PROCESSING else status.HTTP_200_OK)


class ScreeningAgentConfigView(APIView):
    """Integration status (booleans only) and the approved agent script for configuring ElevenLabs."""

    permission_classes = [IsHRStaff]

    def get(self, request):
        browser_mode = settings.SCREENING_VOICE_MODE == "browser"
        data = {
            "integration": configuration_status(),
            "voice_mode": settings.SCREENING_VOICE_MODE,
            "script_version": script.BROWSER_SCRIPT_VERSION if browser_mode else script.SCRIPT_VERSION,
            "dynamic_variables": list(script.DYNAMIC_VARIABLES),
            "calling_policy": {
                "max_attempts": settings.SCREENING_MAX_CALL_ATTEMPTS,
                "retry_interval_minutes": settings.SCREENING_RETRY_INTERVAL_MINUTES,
                "timezone": settings.SCREENING_CALL_TIMEZONE,
                "window_start_hour": settings.SCREENING_CALL_WINDOW_START_HOUR,
                "window_end_hour": settings.SCREENING_CALL_WINDOW_END_HOUR,
            },
            "browser_policy": {
                "max_attempts": settings.SCREENING_MAX_CALL_ATTEMPTS,
                "session_timeout_minutes": settings.SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES,
            },
        }
        if IsHRAdmin().has_permission(request, self):
            data["agent_first_message"] = script.BROWSER_AGENT_FIRST_MESSAGE if browser_mode else script.AGENT_FIRST_MESSAGE
            data["agent_system_prompt"] = script.BROWSER_AGENT_SYSTEM_PROMPT if browser_mode else script.AGENT_SYSTEM_PROMPT
        return Response(data)


class ElevenLabsWebhookView(APIView):
    """Post-call webhook. Authenticated by HMAC signature; it only triggers a provider re-fetch."""

    authentication_classes = []
    permission_classes = [permissions.AllowAny]
    throttle_classes = []

    def post(self, request):
        raw = request.body
        if not verify_elevenlabs_signature(raw, request.headers.get("ElevenLabs-Signature", ""), settings.ELEVENLABS_WEBHOOK_SECRET):
            return Response({"detail": "Invalid signature."}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)
        conversation_id = (payload.get("data") or {}).get("conversation_id")
        attempt = ScreeningCallAttempt.objects.select_related("screening__candidate", "screening__requisition").filter(
            provider_conversation_id=conversation_id, status=CallAttemptStatus.IN_PROGRESS,
        ).first() if conversation_id else None
        if attempt:
            try:
                sync_attempt(attempt)
            except (VoiceConfigurationError, VoiceProviderError) as exc:
                logger.warning("Webhook-triggered sync failed. exception_type=%s", type(exc).__name__)
        return Response({"received": True})
