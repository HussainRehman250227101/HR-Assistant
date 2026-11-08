"""Job requisitions and their controlled lifecycle."""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class RequisitionStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    OPEN = "OPEN", "Open"
    ON_HOLD = "ON_HOLD", "On Hold"
    CLOSED = "CLOSED", "Closed"


class EmploymentType(models.TextChoices):
    FULL_TIME = "FULL_TIME", "Full-time"
    PART_TIME = "PART_TIME", "Part-time"
    CONTRACT = "CONTRACT", "Contract"
    TEMPORARY = "TEMPORARY", "Temporary"
    INTERNSHIP = "INTERNSHIP", "Internship"


class WorkMode(models.TextChoices):
    ONSITE = "ONSITE", "On-site"
    HYBRID = "HYBRID", "Hybrid"
    REMOTE = "REMOTE", "Remote"


class InterviewFormat(models.TextChoices):
    ONSITE = "ONSITE", "On-site"
    VIDEO = "VIDEO", "Video call (WhatsApp)"


class Requisition(models.Model):
    """An approved or draft role request owned by an HR recruiter."""

    reference_code = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=160)
    department = models.CharField(max_length=120)
    location = models.CharField(max_length=160, blank=True)
    employment_type = models.CharField(
        max_length=20, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    work_mode = models.CharField(
        max_length=10, choices=WorkMode.choices, default=WorkMode.ONSITE
    )
    description = models.TextField()
    responsibilities = models.TextField(blank=True)
    required_skills = models.JSONField(default=list, blank=True)
    preferred_skills = models.JSONField(default=list, blank=True)
    screening_questions = models.JSONField(default=list, blank=True)
    # How interviews for this role are held (set by HR at creation). The scheduling agent emails the candidate
    # accordingly: ONSITE -> the role location; VIDEO -> a WhatsApp video call on `interview_whatsapp_number`.
    interview_format = models.CharField(max_length=10, choices=InterviewFormat.choices, default=InterviewFormat.ONSITE)
    interview_whatsapp_number = models.CharField(max_length=20, blank=True)
    minimum_experience_years = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=Decimal("0.0"),
        validators=[MinValueValidator(Decimal("0.0"))],
    )
    education_requirements = models.TextField(blank=True)
    salary_min = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.0"))],
    )
    salary_max = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.0"))],
    )
    currency = models.CharField(max_length=3, default="PKR")
    headcount = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    status = models.CharField(
        max_length=10, choices=RequisitionStatus.choices, default=RequisitionStatus.DRAFT,
        db_index=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requisitions_created",
    )
    hiring_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managed_requisitions",
    )
    target_close_date = models.DateField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "job requisition"
        verbose_name_plural = "job requisitions"

    def __str__(self) -> str:
        return f"{self.title} [{str(self.reference_code)[:8]}]"

    def save(self, *args, **kwargs):
        if self.status == RequisitionStatus.OPEN and self.opened_at is None:
            self.opened_at = timezone.now()
        if self.status == RequisitionStatus.CLOSED and self.closed_at is None:
            self.closed_at = timezone.now()
        super().save(*args, **kwargs)
