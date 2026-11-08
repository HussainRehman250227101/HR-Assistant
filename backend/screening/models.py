"""Screening sessions (SRS §11 Screening entity) and individual outbound call attempts."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ScreeningChannel(models.TextChoices):
    AI_VOICE = "AI_VOICE", "AI voice call (Twilio + ElevenLabs)"
    BROWSER_VOICE = "BROWSER_VOICE", "Browser voice session (ElevenLabs WebRTC, no phone call)"
    HUMAN_LED = "HUMAN_LED", "Human-led screening"


AI_SCREENING_CHANNELS = (ScreeningChannel.AI_VOICE, ScreeningChannel.BROWSER_VOICE)


class ScreeningStatus(models.TextChoices):
    PENDING_CALL = "PENDING_CALL", "Awaiting call attempt"
    CALL_IN_PROGRESS = "CALL_IN_PROGRESS", "Call in progress"
    ANALYZING = "ANALYZING", "Analyzing call transcript"
    ANALYSIS_FAILED = "ANALYSIS_FAILED", "Transcript analysis failed"
    AWAITING_MANUAL_RESULT = "AWAITING_MANUAL_RESULT", "Awaiting human-led screening result"
    AWAITING_HR_REVIEW = "AWAITING_HR_REVIEW", "Awaiting HR review"
    REVIEWED = "REVIEWED", "Reviewed by HR"
    CANCELLED = "CANCELLED", "Cancelled"


ACTIVE_SCREENING_STATUSES = (
    ScreeningStatus.PENDING_CALL,
    ScreeningStatus.CALL_IN_PROGRESS,
    ScreeningStatus.ANALYZING,
    ScreeningStatus.ANALYSIS_FAILED,
    ScreeningStatus.AWAITING_MANUAL_RESULT,
    ScreeningStatus.AWAITING_HR_REVIEW,
)


class CallOutcome(models.TextChoices):
    """SRS §8 `call_status` values."""

    NOT_STARTED = "NOT_STARTED", "Not started"
    COMPLETED = "COMPLETED", "Completed"
    NO_ANSWER = "NO_ANSWER", "No answer"
    BUSY = "BUSY", "Line busy"
    VOICEMAIL = "VOICEMAIL", "Voicemail reached"
    FAILED = "FAILED", "Call failed"
    CONSENT_DECLINED = "CONSENT_DECLINED", "Recording/automated screening declined"
    HUMAN_REQUESTED = "HUMAN_REQUESTED", "Candidate requested a human"
    STOPPED_BY_CANDIDATE = "STOPPED_BY_CANDIDATE", "Candidate asked to stop"
    POOR_AUDIO = "POOR_AUDIO", "Poor audio / could not understand"
    RESCHEDULE_REQUESTED = "RESCHEDULE_REQUESTED", "Candidate asked to reschedule"
    INCOMPLETE = "INCOMPLETE", "Incomplete"
    # Browser voice sessions (Module 16)
    INTERRUPTED = "INTERRUPTED", "Interrupted (connection lost)"
    ABANDONED = "ABANDONED", "Abandoned (never connected or no candidate speech)"


class ScreeningConsent(models.TextChoices):
    NOT_ASKED = "NOT_ASKED", "Not asked"
    GRANTED = "GRANTED", "Granted"
    DECLINED = "DECLINED", "Declined"
    UNCLEAR = "UNCLEAR", "Unclear"


class NextStepRecommendation(models.TextChoices):
    """Recommendation for the human reviewer only; never an automated decision."""

    REVIEW_FOR_INTERVIEW_DECISION = "REVIEW_FOR_INTERVIEW_DECISION", "HR to review for interview decision"
    HUMAN_FOLLOW_UP_REQUIRED = "HUMAN_FOLLOW_UP_REQUIRED", "Human follow-up required"
    OFFER_ALTERNATIVE_SCREENING = "OFFER_ALTERNATIVE_SCREENING", "Offer alternative (human-led) screening"
    RETRY_CALL = "RETRY_CALL", "Retry the call"


class SalaryPeriod(models.TextChoices):
    MONTHLY = "MONTHLY", "Per month"
    ANNUAL = "ANNUAL", "Per year"
    UNSPECIFIED = "UNSPECIFIED", "Period not stated"


class Screening(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="screenings")
    requisition = models.ForeignKey("requisitions.Requisition", on_delete=models.PROTECT, related_name="screenings")
    channel = models.CharField(max_length=16, choices=ScreeningChannel.choices, default=ScreeningChannel.AI_VOICE)
    status = models.CharField(max_length=24, choices=ScreeningStatus.choices, default=ScreeningStatus.PENDING_CALL, db_index=True)
    call_status = models.CharField(max_length=24, choices=CallOutcome.choices, default=CallOutcome.NOT_STARTED)
    consent_status = models.CharField(max_length=10, choices=ScreeningConsent.choices, default=ScreeningConsent.NOT_ASKED)
    ai_disclosure_confirmed = models.BooleanField(null=True, blank=True)
    questions = models.JSONField(default=list)
    script_version = models.CharField(max_length=40)
    max_attempts = models.PositiveSmallIntegerField(default=3)
    attempt_count = models.PositiveSmallIntegerField(default=0)
    next_attempt_not_before = models.DateTimeField(null=True, blank=True)
    # SRS §8 minimum output fields
    question_answer_pairs = models.JSONField(default=list, blank=True)
    candidate_stated_availability = models.TextField(blank=True)
    # Standard answers asked in every screening. *_statement fields hold the candidate's own words,
    # verified against the transcript; the other values are kept only when that quote is verified.
    availability_statement = models.TextField(blank=True)
    expected_salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    expected_salary_currency = models.CharField(max_length=3, blank=True)
    expected_salary_period = models.CharField(max_length=12, choices=SalaryPeriod.choices, blank=True)
    expected_salary_statement = models.TextField(blank=True)
    notice_period = models.CharField(max_length=300, blank=True)
    notice_period_statement = models.TextField(blank=True)
    role_requirement_responses = models.JSONField(default=list, blank=True)
    candidate_questions = models.JSONField(default=list, blank=True)
    unresolved_questions = models.JSONField(default=list, blank=True)
    concise_summary = models.TextField(blank=True)
    recommended_next_step_for_human_review = models.CharField(max_length=32, choices=NextStepRecommendation.choices, blank=True)
    call_timestamp = models.DateTimeField(null=True, blank=True)
    transcript = models.JSONField(default=list, blank=True)
    analysis_warnings = models.JSONField(default=list, blank=True)
    analysis_provider = models.CharField(max_length=40, blank=True)
    analysis_model_version = models.CharField(max_length=120, blank=True)
    analysis_prompt_version = models.CharField(max_length=40, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="screenings_created")
    result_recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="screening_results_recorded"
    )
    result_recorded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("candidate",),
                condition=Q(status__in=ACTIVE_SCREENING_STATUSES),
                name="one_active_screening_per_candidate",
            ),
        ]
        indexes = [models.Index(fields=("status", "created_at")), models.Index(fields=("candidate", "created_at"))]

    def __str__(self):
        return f"{self.candidate} - {self.get_channel_display()} ({self.status})"


class ScreeningDecision(models.TextChoices):
    APPROVE_FOR_INTERVIEW = "APPROVE_FOR_INTERVIEW", "Approve for interview"
    RESCREEN_AI_CALL = "RESCREEN_AI_CALL", "Re-screen with a new AI voice screening"
    RESCREEN_HUMAN_LED = "RESCREEN_HUMAN_LED", "Re-screen with a human-led screening"
    DECLINE = "DECLINE", "Decline (close candidate)"


class ScreeningReview(models.Model):
    """Append-only HR decision on a screening result (FR-08, human gate 2)."""

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    screening = models.OneToOneField(Screening, on_delete=models.PROTECT, related_name="review")
    candidate = models.ForeignKey("candidates.Candidate", on_delete=models.PROTECT, related_name="screening_reviews")
    decision = models.CharField(max_length=24, choices=ScreeningDecision.choices)
    decision_reason = models.TextField(blank=True)
    previous_candidate_status = models.CharField(max_length=40)
    resulting_candidate_status = models.CharField(max_length=40)
    follow_up_screening = models.ForeignKey(
        Screening, on_delete=models.PROTECT, null=True, blank=True, related_name="created_by_review"
    )
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="screening_reviews_decided")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.candidate} - {self.get_decision_display()}"


class CallAttemptStatus(models.TextChoices):
    INITIATING = "INITIATING", "Initiating"
    IN_PROGRESS = "IN_PROGRESS", "In progress"
    ENDED = "ENDED", "Ended"
    FAILED = "FAILED", "Failed to start"


class ScreeningCallAttempt(models.Model):
    """One outbound call or one browser voice session. Append-only audit of every attempt (SRS §13).

    Browser sessions use provider `elevenlabs_webrtc` and have no telephone destination or Twilio SID.
    """

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, db_index=True)
    screening = models.ForeignKey(Screening, on_delete=models.PROTECT, related_name="call_attempts")
    attempt_number = models.PositiveSmallIntegerField()
    provider = models.CharField(max_length=40, default="elevenlabs_twilio")
    destination_masked = models.CharField(max_length=32)
    provider_conversation_id = models.CharField(max_length=128, null=True, blank=True, unique=True)
    provider_call_sid = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=12, choices=CallAttemptStatus.choices, default=CallAttemptStatus.INITIATING)
    outcome = models.CharField(max_length=24, choices=CallOutcome.choices, blank=True)
    provider_status = models.CharField(max_length=32, blank=True)
    telephony_status = models.CharField(max_length=32, blank=True)
    termination_reason = models.CharField(max_length=255, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.CharField(max_length=500, blank=True)
    provider_data_deleted = models.BooleanField(default=False)
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="screening_calls_initiated")
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)
        constraints = [
            models.UniqueConstraint(fields=("screening", "attempt_number"), name="unique_screening_attempt_number"),
        ]

    def __str__(self):
        return f"Attempt {self.attempt_number} for {self.screening_id} ({self.status})"
