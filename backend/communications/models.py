"""SRS §11 CommunicationLog: every outbound candidate email, its approval and delivery state."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class MessageKind(models.TextChoices):
    INTERVIEW_INVITATION = "INTERVIEW_INVITATION", "Interview invitation"
    INTERVIEW_RESCHEDULE = "INTERVIEW_RESCHEDULE", "Interview rescheduled"
    INTERVIEW_CANCELLATION = "INTERVIEW_CANCELLATION", "Interview cancellation"


class ApprovalStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft - awaiting HR approval"
    APPROVED = "APPROVED", "Approved by HR"
    DISCARDED = "DISCARDED", "Discarded"


class SendStatus(models.TextChoices):
    NOT_SENT = "NOT_SENT", "Not sent"
    SENDING = "SENDING", "Sending"
    SENT = "SENT", "Sent (accepted by email provider)"
    FAILED = "FAILED", "Failed"


class CommunicationLog(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="communications")
    interview = models.ForeignKey("scheduling.Interview", on_delete=models.PROTECT, null=True, blank=True, related_name="communications")
    channel = models.CharField(max_length=10, default="EMAIL")
    kind = models.CharField(max_length=24, choices=MessageKind.choices)
    template_version = models.CharField(max_length=40)
    sequence = models.PositiveIntegerField(default=0, help_text="iCalendar SEQUENCE of the interview at draft time.")
    idempotency_key = models.CharField(max_length=120, unique=True)
    recipient = models.EmailField()
    cc = models.JSONField(default=list, blank=True)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    meeting_details = models.JSONField(default=dict, blank=True)
    approval_status = models.CharField(max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.DRAFT, db_index=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="communications_approved")
    approved_at = models.DateTimeField(null=True, blank=True)
    send_status = models.CharField(max_length=10, choices=SendStatus.choices, default=SendStatus.NOT_SENT, db_index=True)
    send_attempts = models.PositiveSmallIntegerField(default=0)
    provider = models.CharField(max_length=120, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="communications_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            # At most one successfully sent message per interview, kind and calendar sequence.
            models.UniqueConstraint(
                fields=("interview", "kind", "sequence"), condition=Q(send_status="SENT"),
                name="one_sent_message_per_interview_kind_sequence",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} to {self.candidate} ({self.send_status})"
