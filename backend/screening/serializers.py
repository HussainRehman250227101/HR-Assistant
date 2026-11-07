from rest_framework import serializers

from .models import (
    CallOutcome, Screening, ScreeningCallAttempt, ScreeningChannel, ScreeningConsent, ScreeningDecision, ScreeningReview,
)


class ScreeningCallAttemptSerializer(serializers.ModelSerializer):
    initiated_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ScreeningCallAttempt
        fields = (
            "public_id", "attempt_number", "provider", "destination_masked", "status", "outcome",
            "provider_status", "telephony_status", "termination_reason", "duration_seconds",
            "error_code", "error_message", "provider_data_deleted", "initiated_by_name",
            "started_at", "ended_at", "last_synced_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_initiated_by_name(obj):
        return obj.initiated_by.get_full_name() or obj.initiated_by.username


class ScreeningReviewSerializer(serializers.ModelSerializer):
    decided_by_name = serializers.SerializerMethodField()
    follow_up_screening = serializers.UUIDField(source="follow_up_screening.public_id", read_only=True, default=None)

    class Meta:
        model = ScreeningReview
        fields = ("public_id", "decision", "decision_reason", "previous_candidate_status", "resulting_candidate_status",
                  "follow_up_screening", "decided_by_name", "created_at")
        read_only_fields = fields

    @staticmethod
    def get_decided_by_name(obj):
        return obj.decided_by.get_full_name() or obj.decided_by.username


class ScreeningReviewRequestSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=ScreeningDecision.choices)
    decision_reason = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class ScreeningSerializer(serializers.ModelSerializer):
    review = serializers.SerializerMethodField()
    candidate_reference = serializers.UUIDField(source="candidate.public_id", read_only=True)
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)
    requisition_reference = serializers.UUIDField(source="requisition.reference_code", read_only=True)
    requisition_title = serializers.CharField(source="requisition.title", read_only=True)
    call_attempts = ScreeningCallAttemptSerializer(many=True, read_only=True)
    created_by_name = serializers.SerializerMethodField()
    result_recorded_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Screening
        fields = (
            "public_id", "candidate_reference", "candidate_name", "requisition_reference", "requisition_title",
            "channel", "status", "call_status", "consent_status", "ai_disclosure_confirmed", "questions",
            "script_version", "max_attempts", "attempt_count", "next_attempt_not_before",
            "question_answer_pairs", "candidate_stated_availability", "role_requirement_responses",
            "candidate_questions", "unresolved_questions", "concise_summary",
            "recommended_next_step_for_human_review", "call_timestamp", "transcript", "analysis_warnings",
            "analysis_provider", "analysis_model_version", "analysis_prompt_version",
            "error_code", "error_message", "created_by_name", "result_recorded_by_name", "result_recorded_at",
            "call_attempts", "review", "created_at", "updated_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_review(obj):
        review = ScreeningReview.objects.filter(screening=obj).select_related("decided_by", "follow_up_screening").first()
        return ScreeningReviewSerializer(review).data if review else None

    @staticmethod
    def get_created_by_name(obj):
        return obj.created_by.get_full_name() or obj.created_by.username

    @staticmethod
    def get_result_recorded_by_name(obj):
        user = obj.result_recorded_by
        return (user.get_full_name() or user.username) if user else None


class ScreeningCreateSerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=ScreeningChannel.choices, default=ScreeningChannel.AI_VOICE)
    start_call_now = serializers.BooleanField(default=False)


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000, trim_whitespace=True)


class ManualAnswerSerializer(serializers.Serializer):
    question_number = serializers.IntegerField(min_value=1)
    answer_status = serializers.ChoiceField(choices=["ANSWERED", "UNCLEAR", "NOT_ASKED", "DECLINED_TO_ANSWER"])
    candidate_statement = serializers.CharField(max_length=4000, required=False, allow_blank=True)
    recruiter_note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


MANUAL_OUTCOMES = [
    CallOutcome.COMPLETED, CallOutcome.NO_ANSWER, CallOutcome.HUMAN_REQUESTED,
    CallOutcome.STOPPED_BY_CANDIDATE, CallOutcome.RESCHEDULE_REQUESTED, CallOutcome.INCOMPLETE,
]


class ManualResultSerializer(serializers.Serializer):
    call_status = serializers.ChoiceField(choices=[(c.value, c.label) for c in MANUAL_OUTCOMES])
    consent_status = serializers.ChoiceField(choices=ScreeningConsent.choices)
    question_answer_pairs = ManualAnswerSerializer(many=True)
    candidate_stated_availability = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    candidate_questions = serializers.ListField(child=serializers.CharField(max_length=500), required=False)
    unresolved_questions = serializers.ListField(child=serializers.CharField(max_length=500), required=False)
    concise_summary = serializers.CharField(max_length=4000)
    call_timestamp = serializers.DateTimeField(required=False)
