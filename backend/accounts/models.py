"""Application user model and HR role definitions."""

from django.contrib.auth.models import AbstractUser
from django.db import models


class UserRole(models.TextChoices):
    ADMIN = "ADMIN", "HR Administrator"
    RECRUITER = "RECRUITER", "HR Recruiter"
    HIRING_MANAGER = "HIRING_MANAGER", "Hiring Manager"


class User(AbstractUser):
    """Custom user model established before the project's first migration."""

    email = models.EmailField(unique=True)
    role = models.CharField(
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.RECRUITER,
        db_index=True,
    )
    department = models.CharField(max_length=120, blank=True)
    job_title = models.CharField(max_length=120, blank=True)

    # Secret in the private calendar-feed URL (scheduling/services/calendar_feed.py); regenerate to revoke.
    calendar_token = models.CharField(max_length=64, null=True, blank=True, unique=True, editable=False)

    REQUIRED_FIELDS = ["email"]

    def __str__(self) -> str:
        return f"{self.get_full_name() or self.username} ({self.role})"
