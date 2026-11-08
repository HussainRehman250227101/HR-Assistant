"""Persistent workflow execution records associated with candidates and evaluations."""

import uuid

from django.conf import settings
from django.db import models


class WorkflowRunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    WAITING_HR_REVIEW = "WAITING_HR_REVIEW", "Waiting for HR Review"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    CANCELLED = "CANCELLED", "Cancelled"


# A candidate may have at most one run in these states (enforced by a database constraint).
ACTIVE_WORKFLOW_STATUSES = (
    WorkflowRunStatus.PENDING,
    WorkflowRunStatus.RUNNING,
    WorkflowRunStatus.WAITING_HR_REVIEW,
)


class WorkflowTrigger(models.TextChoices):
    MANUAL = "MANUAL", "Started by a recruiter"
    AUTOMATIC = "AUTOMATIC", "Started automatically (scheduled scoring)"


class WorkflowRun(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    thread_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    candidate = models.ForeignKey(
        "candidates.Candidate", on_delete=models.PROTECT, related_name="workflow_runs"
    )
    resume_document = models.ForeignKey(
        "candidates.ResumeDocument", on_delete=models.PROTECT, related_name="workflow_runs"
    )
    evaluation = models.ForeignKey(
        "scoring.ResumeEvaluation", on_delete=models.PROTECT,
        null=True, blank=True, related_name="workflow_runs",
    )
    status = models.CharField(
        max_length=24, choices=WorkflowRunStatus.choices,
        default=WorkflowRunStatus.PENDING, db_index=True,
    )
    current_step = models.CharField(max_length=80, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    state_summary = models.JSONField(default=dict, blank=True)
    # Empty for automatic runs started by the scheduled Celery task (trigger=AUTOMATIC).
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="workflow_runs_created",
        null=True, blank=True,
    )
    trigger = models.CharField(
        max_length=12, choices=WorkflowTrigger.choices, default=WorkflowTrigger.MANUAL, db_index=True,
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("candidate", "status")),
            models.Index(fields=("status", "created_at")),
        ]
        constraints = [
            # Prevents duplicate scoring when a recruiter and the scheduled task (or two workers) race.
            models.UniqueConstraint(
                fields=("candidate",),
                condition=models.Q(status__in=ACTIVE_WORKFLOW_STATUSES),
                name="workflowrun_one_active_per_candidate",
            ),
        ]

    def __str__(self):
        return f"{self.candidate} — {self.get_status_display()} ({str(self.public_id)[:8]})"
