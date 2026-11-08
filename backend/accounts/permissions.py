"""Reusable role-based API permissions.

Roles: HR Administrator and Hiring Manager have full access (they run the hiring process and may also interview).
HR Recruiter is an interviewer only: they see the candidates assigned to them and manage their own availability.
"""

from rest_framework.permissions import BasePermission

from .models import UserRole

FULL_ACCESS_ROLES = (UserRole.ADMIN, UserRole.HIRING_MANAGER)


def has_full_access(user) -> bool:
    """HR Administrator or Hiring Manager (superusers count as administrators)."""
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and (user.is_superuser or getattr(user, "role", None) in FULL_ACCESS_ROLES)
    )


class IsHRAdmin(BasePermission):
    message = "HR Administrator role is required."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role == UserRole.ADMIN)
        )


class IsHRStaff(BasePermission):
    """Full-access staff: HR Administrator or Hiring Manager."""

    message = "HR Administrator or Hiring Manager role is required."

    def has_permission(self, request, view) -> bool:
        return has_full_access(request.user)
