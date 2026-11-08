from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import CALENDAR_SOURCE_LABEL, AvailabilitySlot, Interview, InterviewMode
from .services.slots import SchedulingError, local_window_to_utc


def _name(user):
    return (user.get_full_name() or user.username) if user else None


class LocalWindowSerializer(serializers.Serializer):
    date = serializers.DateField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()


def windows_to_utc(windows, tz_name):
    result = []
    for window in windows:
        try:
            start, end = local_window_to_utc(window["date"], window["start_time"], window["end_time"], tz_name)
        except SchedulingError as exc:
            raise serializers.ValidationError({"windows": str(exc)}) from exc
        result.append({"start": start.isoformat(), "end": end.isoformat()})
    return result


class AvailabilitySlotSerializer(serializers.ModelSerializer):
    interviewer_name = serializers.SerializerMethodField()
    source_label = serializers.SerializerMethodField()

    class Meta:
        model = AvailabilitySlot
        fields = ("public_id", "interviewer", "interviewer_name", "start", "end", "timezone", "source", "source_label", "created_at")
        read_only_fields = fields

    @staticmethod
    def get_interviewer_name(obj):
        return _name(obj.interviewer)

    @staticmethod
    def get_source_label(obj):
        return CALENDAR_SOURCE_LABEL


class AvailabilityCreateSerializer(LocalWindowSerializer):
    interviewer = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.filter(is_active=True), required=False)
    timezone = serializers.CharField(max_length=64)


class InterviewSerializer(serializers.ModelSerializer):
    candidate_reference = serializers.UUIDField(source="candidate.public_id", read_only=True)
    candidate_name = serializers.CharField(source="candidate.full_name", read_only=True)
    requisition_title = serializers.CharField(source="requisition.title", read_only=True)
    interviewer_name = serializers.SerializerMethodField()
    interviewer_email = serializers.EmailField(source="interviewer.email", read_only=True)
    calendar_source_label = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Interview
        fields = (
            "public_id", "candidate_reference", "candidate_name", "requisition_title", "interviewer", "interviewer_name",
            "interviewer_email", "status", "duration_minutes", "timezone", "mode", "meeting_link", "location",
            "contact_whatsapp", "auto_scheduled", "candidate_availability_note", "candidate_windows", "proposed_slots", "calendar_source",
            "calendar_source_label", "confirmed_start", "confirmed_end", "candidate_confirmed_at",
            "interviewer_confirmed_at", "cancellation_reason", "sequence", "created_by_name", "created_at", "updated_at",
        )
        read_only_fields = fields

    @staticmethod
    def get_interviewer_name(obj):
        return _name(obj.interviewer)

    @staticmethod
    def get_created_by_name(obj):
        return _name(obj.created_by)

    @staticmethod
    def get_calendar_source_label(obj):
        return CALENDAR_SOURCE_LABEL


class InterviewPlanSerializer(serializers.Serializer):
    interviewer = serializers.PrimaryKeyRelatedField(queryset=get_user_model().objects.filter(is_active=True))
    duration_minutes = serializers.IntegerField(min_value=15, max_value=240)
    timezone = serializers.CharField(max_length=64)
    mode = serializers.ChoiceField(choices=InterviewMode.choices)
    meeting_link = serializers.URLField(required=False, allow_blank=True, max_length=500)
    location = serializers.CharField(required=False, allow_blank=True, max_length=255)
    contact_whatsapp = serializers.CharField(required=False, allow_blank=True, max_length=20)
    candidate_availability_note = serializers.CharField(required=False, allow_blank=True, max_length=2000)
    candidate_windows = LocalWindowSerializer(many=True, allow_empty=False)

    def validate(self, attrs):
        attrs["candidate_windows"] = windows_to_utc(attrs["candidate_windows"], attrs["timezone"])
        return attrs


class InterviewReproposeSerializer(InterviewPlanSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.required = False

    def validate(self, attrs):
        if "candidate_windows" in attrs:
            tz_name = attrs.get("timezone") or self.context["interview"].timezone
            attrs["candidate_windows"] = windows_to_utc(attrs["candidate_windows"], tz_name)
        return attrs


class ConfirmSlotSerializer(serializers.Serializer):
    slot_start = serializers.DateTimeField()
    candidate_confirmed = serializers.BooleanField()
    interviewer_confirmed = serializers.BooleanField()


class CancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=1000)
