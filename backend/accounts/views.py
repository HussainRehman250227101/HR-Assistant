from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenBlacklistView

from .models import User, UserRole
from .permissions import IsHRStaff
from .serializers import UserProfileSerializer


class MeView(APIView):
    """Return the authenticated user's own profile."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(UserProfileSerializer(request.user).data)


class UserDirectoryView(APIView):
    """Minimal staff directory (for hiring-manager / interviewer pickers). HR Administrators and Hiring Managers only."""

    permission_classes = [IsHRStaff]

    def get(self, request):
        qs = User.objects.filter(is_active=True).order_by("first_name", "last_name", "username")
        role = request.query_params.get("role")
        if role:
            if role not in UserRole.values:
                return Response({"role": "Invalid role."}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(role=role)
        return Response(UserProfileSerializer(qs, many=True).data)


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
