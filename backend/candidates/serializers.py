"""Candidate, resume and browsable batch-upload serializers."""

from rest_framework import serializers

from requisitions.models import Requisition, RequisitionStatus
from .models import Candidate, CandidateEvent, ResumeDocument
from .validators import validate_resume_upload


class ResumeDocumentSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = ResumeDocument
        fields = ("public_id", "original_filename", "content_type", "file_size", "processing_status", "warning_messages", "error_code", "error_message", "created_at", "processed_at")
        read_only_fields = fields


class CandidateSerializer(serializers.ModelSerializer):
    requisition = serializers.PrimaryKeyRelatedField(queryset=Requisition.objects.filter(status=RequisitionStatus.OPEN))
    created_by = serializers.IntegerField(source="created_by_id", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    resume_documents = ResumeDocumentSummarySerializer(many=True, read_only=True)

    class Meta:
        model = Candidate
        fields = (
            "public_id", "requisition", "full_name", "display_name", "email", "phone",
            "location", "linkedin_url", "source", "contact_consent_status",
            "recording_consent_status", "consent_preferences", "current_status",
            "identity_review_required", "auto_filled_fields", "closed_reason", "personal_data_erased_at", "created_by", "created_by_name",
            "resume_documents", "created_at", "updated_at",
        )
        read_only_fields = ("public_id", "display_name", "current_status", "identity_review_required", "auto_filled_fields", "closed_reason", "personal_data_erased_at", "created_by", "created_by_name", "resume_documents", "created_at", "updated_at")

    def update(self, instance, validated_data):
        # A field a recruiter edits is no longer "from the resume".
        edited = {f for f, v in validated_data.items() if f in (instance.auto_filled_fields or []) and v != getattr(instance, f)}
        if edited:
            instance.auto_filled_fields = [f for f in instance.auto_filled_fields if f not in edited]
        return super().update(instance, validated_data)

    @staticmethod
    def get_created_by_name(obj):
        return obj.created_by.get_full_name() or obj.created_by.username

    @staticmethod
    def get_display_name(obj):
        return obj.full_name or f"Candidate {str(obj.public_id)[:8]}"

    def validate_email(self, value):
        return value.strip().lower() if value else None

    def validate_phone(self, value):
        return value.strip()

    def validate(self, attrs):
        requisition = attrs.get("requisition", getattr(self.instance, "requisition", None))
        email = attrs.get("email", getattr(self.instance, "email", None))
        if requisition and email:
            qs = Candidate.objects.filter(requisition=requisition, email__iexact=email)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"email": "This candidate email is already registered for the requisition."})
        if "consent_preferences" in attrs and not isinstance(attrs["consent_preferences"], dict):
            raise serializers.ValidationError({"consent_preferences": "Consent preferences must be a JSON object."})
        return attrs


class ResumeUploadSerializer(serializers.Serializer):
    file = serializers.FileField(help_text="Select one PDF or DOCX resume.")

    def validate_file(self, value):
        validate_resume_upload(value)
        return value


class ResumeBatchUploadSerializer(serializers.Serializer):
    # Browsable API file picker. Submit once per resume; batch API clients can send repeated parts.
    files = serializers.FileField(
        required=False,
        allow_empty_file=False,
        help_text="Select one PDF or DOCX file. Submit once per resume in the browsable API.",
    )

    def validate_files(self, value):
        validate_resume_upload(value)
        return value


class CandidateEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = CandidateEvent
        fields = ("id", "event_type", "actor_name", "details", "created_at")
        read_only_fields = fields

    @staticmethod
    def get_actor_name(obj):
        return (obj.actor.get_full_name() or obj.actor.username) if obj.actor else None


class ResumeDocumentDetailSerializer(serializers.ModelSerializer):
    candidate_id = serializers.UUIDField(source="candidate.public_id", read_only=True)

    class Meta:
        model = ResumeDocument
        fields = ("public_id", "candidate_id", "original_filename", "content_type", "file_size", "processing_status", "extraction_metadata", "warning_messages", "error_code", "error_message", "processing_started_at", "processed_at", "created_at")
        read_only_fields = fields
