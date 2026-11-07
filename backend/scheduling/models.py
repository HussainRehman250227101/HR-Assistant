"""Interviewer availability and interviews (SRS §11 Interview entity, Agent 3)."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

CALENDAR_SOURCE_INTERNAL = "INTERNAL_AVAILABILITY"
CALENDAR_SOURCE_LABEL = (
    "Internal availability calendar (maintained in this application; no Google/Microsoft calendar is connected)"
)


class AvailabilitySlot(models.Model):
    """A window in which an interviewer is free. Times stored in UTC; `timezone` is the entry time zone."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="availability_slots")
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    timezone = models.CharField(max_length=64)
    source = models.CharField(max_length=32, default=CALENDAR_SOURCE_INTERNAL)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="availability_slots_created")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("start",)
        constraints = [models.CheckConstraint(condition=Q(end__gt=models.F("start")), name="availability_end_after_start")]


class InterviewMode(models.TextChoices):
    VIDEO = "VIDEO", "Video call"
    ONSITE = "ONSITE", "On-site"
    PHONE = "PHONE", "Phone"


class InterviewStatus(models.TextChoices):
    PROPOSED = "PROPOSED", "Slots proposed"
    NEEDS_HR_COORDINATION = "NEEDS_HR_COORDINATION", "No shared availability - HR to coordinate"
    SLOT_CONFIRMED = "SLOT_CONFIRMED", "Slot confirmed with candidate and interviewer"
    SCHEDULED = "SCHEDULED", "Invitation sent - scheduled"
    CANCELLED = "CANCELLED", "Cancelled"


ACTIVE_INTERVIEW_STATUSES = (
    InterviewStatus.PROPOSED, InterviewStatus.NEEDS_HR_COORDINATION,
    InterviewStatus.SLOT_CONFIRMED, InterviewStatus.SCHEDULED,
)
BOOKED_STATUSES = (InterviewStatus.SLOT_CONFIRMED, InterviewStatus.SCHEDULED)


class Interview(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="interviews")
    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.PROTECT, related_name="interviews")
    interviewer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="interviews_assigned")
    status = models.CharField(max_length=24, choices=InterviewStatus.choices, default=InterviewStatus.PROPOSED, db_index=True)
    duration_minutes = models.PositiveSmallIntegerField(default=45)
    timezone = models.CharField(max_length=64, help_text="Candidate time zone (IANA).")
    mode = models.CharField(max_length=8, choices=InterviewMode.choices, default=InterviewMode.VIDEO)
    meeting_link = models.URLField(max_length=500, blank=True)
    location = models.CharField(max_length=255, blank=True)
    candidate_availability_note = models.TextField(blank=True)
    candidate_windows = models.JSONField(default=list, blank=True)
    proposed_slots = models.JSONField(default=list, blank=True)
    calendar_source = models.CharField(max_length=32, default=CALENDAR_SOURCE_INTERNAL)
    confirmed_start = models.DateTimeField(null=True, blank=True)
    confirmed_end = models.DateTimeField(null=True, blank=True)
    candidate_confirmed_at = models.DateTimeField(null=True, blank=True)
    interviewer_confirmed_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    sequence = models.PositiveIntegerField(default=0, help_text="Incremented on each reschedule after an invitation was sent.")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="interviews_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("candidate",), condition=Q(status__in=ACTIVE_INTERVIEW_STATUSES),
                name="one_active_interview_per_candidate",
            ),
        ]
        indexes = [models.Index(fields=("interviewer", "confirmed_start"))]

    def __str__(self):
        return f"Interview {str(self.public_id)[:8]} - {self.candidate} ({self.status})"
