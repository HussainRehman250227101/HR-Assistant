import logging

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage, get_connection
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.throttling import AnonRateThrottle
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView

from .models import User, UserRole
from .permissions import IsHRAdmin, IsHRStaff
from audit.models import log_audit
from .serializers import ForgotPasswordSerializer, PasswordChangeSerializer, ResetPasswordSerializer, RecruiterCreateSerializer, RecruiterUpdateSerializer, UserProfileSerializer

logger = logging.getLogger(__name__)


class MeView(APIView):
    """Return the authenticated user's own profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)


class UserDirectoryView(APIView):
    """Staff directory (pickers, recruiter list) and creation of HR Recruiter accounts. HR Administrators and Hiring Managers only."""

    permission_classes = [IsHRStaff]

    def get(self, request):
        qs = User.objects.order_by("first_name", "last_name", "username")
        if request.query_params.get("include_inactive") != "1":
            qs = qs.filter(is_active=True)
        role = request.query_params.get("role")
        if role:
            if role not in UserRole.values:
                return Response({"role": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(role=role)
        return Response(UserProfileSerializer(qs, many=True).data)

    def post(self, request):
        """Add a new HR Recruiter (interviewer-only role). Other roles cannot be created here."""
        serializer = RecruiterCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.create_user(
            username=data["username"], email=data["email"], password=data["password"], first_name=data["first_name"],
            last_name=data["last_name"], department=data["department"], job_title=data["job_title"], role=UserRole.RECRUITER,
        )
        log_audit(request.user, "RECRUITER_CREATED", "user", user.pk, role=user.role)
        return Response(UserProfileSerializer(user).data, status=status.HTTP_201_CREATED)


class RecruiterDetailView(APIView):
    """Manage one HR Recruiter account: edit (HR Administrator or Hiring Manager), activate / deactivate / delete (administrator).

    * Deactivating keeps the account and its history; the person cannot sign in and is no longer offered as an
      interviewer, and their future availability is deleted. It is refused while they have upcoming interviews:
      reassign those first (interview reassign endpoint).
    * Delete removes the account for good, only when it has no history (no interviews, feedback, events or
      approvals). Otherwise deactivate it.
    """

    permission_classes = [IsHRStaff]

    @staticmethod
    def _target(pk):
        target = get_object_or_404(User, pk=pk)
        if target.role != UserRole.RECRUITER or target.is_superuser:
            raise ValidationError({"detail": "Only HR Recruiter accounts can be managed here."})
        return target

    @staticmethod
    def _pending_interviews(target):
        from django.db.models import Q
        from django.utils import timezone
        from scheduling.models import ACTIVE_INTERVIEW_STATUSES, Interview

        return Interview.objects.filter(interviewer=target, status__in=ACTIVE_INTERVIEW_STATUSES).filter(
            Q(confirmed_start__isnull=True) | Q(confirmed_start__gte=timezone.now())).count()

    def _blocked(self, target, pending):
        name = target.get_full_name() or target.username
        return Response({"detail": f"{name} still has {pending} upcoming interview(s). Reassign them to another interviewer first.",
                         "pending_interviews": pending}, status=status.HTTP_409_CONFLICT)

    def patch(self, request, pk):
        from django.db import transaction
        from django.utils import timezone
        from scheduling.models import AvailabilitySlot

        target = self._target(pk)
        serializer = RecruiterUpdateSerializer(data=request.data, context={"target": target})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if "is_active" in data and not IsHRAdmin().has_permission(request, self):
            raise PermissionDenied("Only an HR Administrator can activate or deactivate accounts.")
        with transaction.atomic():
            if "is_active" in data and data["is_active"] != target.is_active:
                if not data["is_active"]:
                    pending = self._pending_interviews(target)
                    if pending:
                        return self._blocked(target, pending)
                    AvailabilitySlot.objects.filter(interviewer=target, end__gt=timezone.now()).delete()
                target.is_active = data["is_active"]
                log_audit(request.user, "RECRUITER_ACTIVATED" if target.is_active else "RECRUITER_DEACTIVATED", "user", target.pk)
            changed = [f for f in ("first_name", "last_name", "email", "department", "job_title") if f in data and getattr(target, f) != data[f]]
            for field in changed:
                setattr(target, field, data[field])
            if changed:
                log_audit(request.user, "RECRUITER_UPDATED", "user", target.pk, fields=changed)
            target.save()
        return Response(UserProfileSerializer(target).data)

    def delete(self, request, pk):
        from django.db import transaction
        from django.db.models import ProtectedError
        from audit.models import AuditEvent
        from candidates.models import CandidateEvent

        if not IsHRAdmin().has_permission(request, self):
            raise PermissionDenied("Only an HR Administrator can delete accounts.")
        target = self._target(pk)
        pending = self._pending_interviews(target)
        if pending:
            return self._blocked(target, pending)
        has_history = CandidateEvent.objects.filter(actor=target).exists() or AuditEvent.objects.filter(actor=target).exists()
        try:
            with transaction.atomic():
                if has_history:
                    raise ProtectedError("history", [])
                snapshot = {"username": target.username, "email": target.email}
                target_id = target.pk
                target.delete()
                log_audit(request.user, "RECRUITER_DELETED", "user", target_id, **snapshot)
        except ProtectedError:
            return Response({"detail": "This account has interview or activity history, so it cannot be deleted. Deactivate it instead."},
                            status=status.HTTP_409_CONFLICT)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    """Any signed-in user changes their own password."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=("password",))
        log_audit(request.user, "PASSWORD_CHANGED", "user", request.user.pk)
        return Response({"detail": "Your password was changed."})


class PasswordResetThrottle(AnonRateThrottle):
    scope = "password_reset"


class ForgotPasswordView(APIView):
    """Email a one-hour reset link. The answer is always the same, so it never reveals whether an address is registered."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=serializer.validated_data["email"], is_active=True).first()
        if user:
            try:
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                link = f"{settings.FRONTEND_BASE_URL.rstrip('/')}/reset-password?uid={uid}&token={default_token_generator.make_token(user)}"
                minutes = settings.PASSWORD_RESET_TIMEOUT // 60
                EmailMessage(
                    subject="Reset your HR Assistant password",
                    body=(f"Hi {user.first_name or user.username},\n\nWe received a request to reset your password. "
                          f"Open this link within {minutes} minutes to choose a new one:\n{link}\n\n"
                          "If you did not ask for this, you can ignore this email; your password stays the same.\n\n"
                          f"The {settings.SCREENING_ORGANIZATION_NAME} Recruiting Team"),
                    from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email], connection=get_connection(),
                ).send(fail_silently=False)
                log_audit(None, "PASSWORD_RESET_REQUESTED", "user", user.pk)
            except Exception as exc:  # the caller must not learn whether the address exists or the email failed
                logger.warning("Password reset email failed. exception_type=%s", type(exc).__name__)
        return Response({"detail": "If that email address belongs to an account, a reset link has been sent."})


class ResetPasswordView(APIView):
    """Set a new password with the emailed link (for every role)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordResetThrottle]

    def post(self, request):
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        user.set_password(serializer.validated_data["new_password"])
        user.save(update_fields=("password",))  # also invalidates the link: the token is bound to the old password hash
        log_audit(None, "PASSWORD_RESET_COMPLETED", "user", user.pk)
        return Response({"detail": "Your password was reset. You can now sign in."})


class LogoutView(TokenBlacklistView):
    """Blacklist the submitted refresh token (JWT logout)."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if not request.data.get("refresh"):
            return Response(
                {"detail": "A refresh token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().post(request, *args, **kwargs)
