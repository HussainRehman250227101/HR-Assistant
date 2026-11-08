from rest_framework import serializers

from .models import CommunicationLog


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class CommunicationLogSerializer(serializers.ModelSerializer):
    candidate_reference = serializers.UUIDField(source="candidate.public_id", read_only=True)
    interview_reference = serializers.UUIDField(source="interview.public_id", read_only=True, default=None)
    approved_by_name = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = CommunicationLog
        fields = (
            "public_id", "candidate_reference", "interview_reference", "channel", "kind", "template_version",
            "sequence", "recipient", "cc", "subject", "body", "meeting_details", "approval_status",
            "approved_by_name", "approved_at", "auto_sent", "send_status", "send_attempts", "provider", "provider_message_id",
            "sent_at", "error_code", "error_message", "created_by_name", "created_at", "updated_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_approved_by_name(obj):
        return _name(obj.approved_by)

    @staticmethod
    def get_created_by_name(obj):
        return _name(obj.created_by)


class DraftUpdateSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=255)
    body = serializers.CharField(max_length=10000)


class ApproveSendSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Explicit confirmation is required before sending.")
        return value
