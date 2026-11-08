"""Validation and response serializers for shortlist review."""

from rest_framework import serializers

from .models import ShortlistDecision, ShortlistReview


class ShortlistDecisionRequestSerializer(serializers.Serializer):
    evaluation = serializers.UUIDField(help_text="Public UUID of the candidate's latest AI evaluation.")
    decision = serializers.ChoiceField(choices=ShortlistDecision.choices)
    # Approval is one click ("Approve this candidate"): the reason is optional. Declines and holds need one (FR-04).
    decision_reason = serializers.CharField(max_length=2000, trim_whitespace=True, required=False, allow_blank=True, default="")
    score_override = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=100)
    score_override_reason = serializers.CharField(required=False, allow_blank=True, max_length=1000)
    # Kept for API compatibility. Approving now confirms the details read from the resume.
    identity_verified = serializers.BooleanField(required=False, default=False)
    identity_review_reason = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")

    def validate(self, attrs):
        decision = attrs["decision"]
        reason = attrs.get("decision_reason", "").strip()
        if decision in {ShortlistDecision.DECLINE, ShortlistDecision.HOLD_FOR_REVIEW} and not reason:
            raise serializers.ValidationError({"decision_reason": "A reason is required for a decline or manual-review hold."})
        override = attrs.get("score_override")
        override_reason = attrs.get("score_override_reason", "").strip()
        if override is not None and not override_reason:
            raise serializers.ValidationError({"score_override_reason": "Explain every manual score override."})
        if override is None and override_reason:
            raise serializers.ValidationError({"score_override": "Provide a score override when supplying an override reason."})
        if attrs.get("identity_verified") and decision != ShortlistDecision.APPROVE_FOR_SCREENING:
            raise serializers.ValidationError({"identity_verified": "Identity confirmation is only relevant when approving screening."})
        return attrs


class ShortlistReviewSerializer(serializers.ModelSerializer):
    candidate_reference = serializers.UUIDField(source="candidate.public_id", read_only=True)
    evaluation_reference = serializers.UUIDField(source="evaluation.public_id", read_only=True)
    decided_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ShortlistReview
        fields = (
            "public_id", "candidate_reference", "evaluation_reference", "decision",
            "decision_reason", "score_override", "score_override_reason",
            "previous_candidate_status", "resulting_candidate_status",
            "decided_by_name", "created_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_decided_by_name(obj):
        return obj.decided_by.get_full_name() or obj.decided_by.username
