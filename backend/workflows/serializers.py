from rest_framework import serializers

from .models import WorkflowRun


class WorkflowRunSerializer(serializers.ModelSerializer):
    candidate_reference = serializers.UUIDField(source="candidate.public_id", read_only=True)
    resume_reference = serializers.UUIDField(source="resume_document.public_id", read_only=True)
    evaluation_reference = serializers.UUIDField(source="evaluation.public_id", read_only=True)

    class Meta:
        model = WorkflowRun
        fields = (
            "public_id", "candidate_reference", "resume_reference",
            "evaluation_reference", "thread_id", "trigger", "status", "current_step",
            "error_code", "error_message", "state_summary",
            "started_at", "completed_at", "created_at", "updated_at",
        )
        read_only_fields = fields
