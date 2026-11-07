"""Candidate, resume-document and audit-event data models."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


def resume_upload_path(instance, filename):
    suffix = ".docx" if filename.lower().endswith(".docx") else ".pdf"
    return f"resumes/{instance.candidate.public_id}/{uuid.uuid4().hex}{suffix}"


class CandidateStatus(models.TextChoices):
    RESUME_RECEIVED = "RESUME_RECEIVED", "Resume Received"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW", "Needs Manual Review"
    SCORED_HR_REVIEW = "SCORED_HR_REVIEW", "Scored — HR Review"
    APPROVED_FOR_SCREENING = "APPROVED_FOR_SCREENING", "Approved for Screening"
    SCREENING_SCHEDULED_PENDING = "SCREENING_SCHEDULED_PENDING", "Screening Scheduled / Pending"
    SCREENING_COMPLETED_HR_REVIEW = "SCREENING_COMPLETED_HR_REVIEW", "Screening Completed — HR Review"
    APPROVED_FOR_INTERVIEW = "APPROVED_FOR_INTERVIEW", "Approved for Interview"
    INTERVIEW_PROPOSED = "INTERVIEW_PROPOSED", "Interview Proposed"
    INTERVIEW_SCHEDULED = "INTERVIEW_SCHEDULED", "Interview Scheduled"
    CLOSED = "CLOSED", "Closed"


class ConsentStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    GRANTED = "GRANTED", "Granted"
    DECLINED = "DECLINED", "Declined"


class CandidateSource(models.TextChoices):
    RESUME_UPLOAD = "RESUME_UPLOAD", "Resume Upload"
    REFERRAL = "REFERRAL", "Referral"
    CAREER_PAGE = "CAREER_PAGE", "Career Page"
    OTHER = "OTHER", "Other"


class ResumeProcessingStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    NEEDS_MANUAL_REVIEW = "NEEDS_MANUAL_REVIEW", "Needs Manual Review"
    FAILED = "FAILED", "Failed"


class Candidate(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.PROTECT, related_name="candidates")
    full_name = models.CharField(max_length=180, blank=True)
    email = models.EmailField(max_length=254, blank=True, null=True)
    phone = models.CharField(max_length=32, blank=True)
    location = models.CharField(max_length=160, blank=True)
    linkedin_url = models.URLField(max_length=500, blank=True)
    source = models.CharField(max_length=20, choices=CandidateSource.choices, default=CandidateSource.RESUME_UPLOAD)
    contact_consent_status = models.CharField(max_length=10, choices=ConsentStatus.choices, default=ConsentStatus.PENDING)
    recording_consent_status = models.CharField(max_length=10, choices=ConsentStatus.choices, default=ConsentStatus.PENDING)
    consent_preferences = models.JSONField(default=dict, blank=True)
    current_status = models.CharField(max_length=40, choices=CandidateStatus.choices, default=CandidateStatus.RESUME_RECEIVED, db_index=True)
    identity_review_required = models.BooleanField(default=False)
    closed_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="candidates_created")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("requisition", "email"),
                condition=Q(email__isnull=False) & ~Q(email=""),
                name="unique_candidate_email_per_requisition",
            ),
        ]
        indexes = [
            models.Index(fields=("requisition", "current_status")),
            models.Index(fields=("created_at",)),
        ]

    def __str__(self):
        return self.full_name or f"Candidate {str(self.public_id)[:8]}"


class ResumeDocument(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="resume_documents")
    file = models.FileField(upload_to=resume_upload_path)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120)
    file_size = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64, db_index=True)
    processing_status = models.CharField(max_length=24, choices=ResumeProcessingStatus.choices, default=ResumeProcessingStatus.PENDING, db_index=True)
    extracted_text = models.TextField(blank=True)
    extraction_metadata = models.JSONField(default=dict, blank=True)
    warning_messages = models.JSONField(default=list, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="resume_documents_uploaded")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("candidate", "sha256"), name="unique_resume_checksum_per_candidate"),
        ]
        indexes = [models.Index(fields=("processing_status", "created_at"))]

    def __str__(self):
        return f"{self.original_filename} ({self.processing_status})"


class CandidateEvent(models.Model):
    class EventType(models.TextChoices):
        CANDIDATE_CREATED = "CANDIDATE_CREATED", "Candidate Created"
        CANDIDATE_UPDATED = "CANDIDATE_UPDATED", "Candidate Updated"
        RESUME_UPLOADED = "RESUME_UPLOADED", "Resume Uploaded"
        RESUME_EXTRACTION_COMPLETED = "RESUME_EXTRACTION_COMPLETED", "Resume Extraction Completed"
        RESUME_EXTRACTION_REVIEW = "RESUME_EXTRACTION_REVIEW", "Resume Requires Manual Review"
        RESUME_EXTRACTION_FAILED = "RESUME_EXTRACTION_FAILED", "Resume Extraction Failed"
        RESUME_RETRY_QUEUED = "RESUME_RETRY_QUEUED", "Resume Retry Queued"
        STATUS_CHANGED = "STATUS_CHANGED", "Candidate Status Changed"
        RESUME_SCORED = "RESUME_SCORED", "Resume Scored"
        SHORTLIST_DECISION_RECORDED = "SHORTLIST_DECISION_RECORDED", "Shortlist Decision Recorded"
        CANDIDATE_IDENTITY_REVIEWED = "CANDIDATE_IDENTITY_REVIEWED", "Candidate Identity Reviewed"
        WORKFLOW_STARTED = "WORKFLOW_STARTED", "Workflow Started"
        WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED", "Workflow Completed"
        WORKFLOW_FAILED = "WORKFLOW_FAILED", "Workflow Failed"
        SCREENING_CREATED = "SCREENING_CREATED", "Screening Created"
        SCREENING_CALL_STARTED = "SCREENING_CALL_STARTED", "Screening Call Started"
        SCREENING_CALL_FAILED = "SCREENING_CALL_FAILED", "Screening Call Failed To Start"
        SCREENING_CALL_ENDED = "SCREENING_CALL_ENDED", "Screening Call Ended"
        SCREENING_ANALYSIS_FAILED = "SCREENING_ANALYSIS_FAILED", "Screening Analysis Failed"
        SCREENING_RESULT_RECORDED = "SCREENING_RESULT_RECORDED", "Screening Result Recorded"
        SCREENING_ESCALATED = "SCREENING_ESCALATED", "Screening Escalated To HR"
        SCREENING_CANCELLED = "SCREENING_CANCELLED", "Screening Cancelled"
        CONSENT_UPDATED = "CONSENT_UPDATED", "Consent Updated"

    candidate = models.ForeignKey(Candidate, on_delete=models.CASCADE, related_name="events")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="candidate_events")
    event_type = models.CharField(max_length=40, choices=EventType.choices, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [models.Index(fields=("candidate", "created_at"))]
