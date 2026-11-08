"""API serializers for requisition data."""

import re
from decimal import Decimal

from rest_framework import serializers

from accounts.models import User, UserRole
from .models import InterviewFormat, Requisition


class RequisitionSerializer(serializers.ModelSerializer):
    created_by = serializers.IntegerField(source="created_by_id", read_only=True)
    created_by_name = serializers.SerializerMethodField()
    hiring_manager = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=UserRole.HIRING_MANAGER),
        required=False,
        allow_null=True,
    )
    hiring_manager_name = serializers.SerializerMethodField()
    required_skills = serializers.ListField(
        child=serializers.CharField(max_length=80, trim_whitespace=True),
        required=False, allow_empty=True, max_length=50,
    )
    preferred_skills = serializers.ListField(
        child=serializers.CharField(max_length=80, trim_whitespace=True),
        required=False, allow_empty=True, max_length=50,
    )
    screening_questions = serializers.ListField(
        child=serializers.CharField(max_length=500, trim_whitespace=True),
        required=False, allow_empty=True, max_length=30,
    )
    minimum_experience_years = serializers.DecimalField(
        max_digits=4, decimal_places=1, min_value=0,
        required=False, default=Decimal("0.0"),
    )
    salary_min = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    salary_max = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=0, required=False, allow_null=True
    )
    headcount = serializers.IntegerField(min_value=1, required=False, default=1)

    class Meta:
        model = Requisition
        fields = (
            "id", "reference_code", "title", "department", "location",
            "employment_type", "work_mode", "description", "responsibilities",
            "required_skills", "preferred_skills", "screening_questions",
            "interview_format", "interview_whatsapp_number", "minimum_experience_years", "education_requirements", "salary_min",
            "salary_max", "currency", "headcount", "status", "created_by",
            "created_by_name", "hiring_manager", "hiring_manager_name",
            "target_close_date", "opened_at", "closed_at", "created_at", "updated_at",
        )
        read_only_fields = (
            "id", "reference_code", "created_by", "created_by_name",
            "hiring_manager_name", "opened_at", "closed_at", "created_at", "updated_at",
        )

    @staticmethod
    def get_created_by_name(obj):
        return obj.created_by.get_full_name() or obj.created_by.username

    @staticmethod
    def get_hiring_manager_name(obj):
        if not obj.hiring_manager:
            return None
        return obj.hiring_manager.get_full_name() or obj.hiring_manager.username

    def _validate_unique_text_list(self, value, label):
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise serializers.ValidationError(f"{label} cannot contain blank entries.")
        if len({item.casefold() for item in cleaned}) != len(cleaned):
            raise serializers.ValidationError(f"{label} must not contain duplicates.")
        return cleaned

    def validate_currency(self, value):
        value = value.strip().upper()
        if len(value) != 3 or not value.isalpha():
            raise serializers.ValidationError("Enter a valid three-letter currency code.")
        return value

    def validate_required_skills(self, value):
        return self._validate_unique_text_list(value, "Required skills")

    def validate_preferred_skills(self, value):
        return self._validate_unique_text_list(value, "Preferred skills")

    def validate_screening_questions(self, value):
        return self._validate_unique_text_list(value, "Screening questions")

    def validate_interview_whatsapp_number(self, value):
        value = (value or "").strip()
        if not value:
            return ""
        digits = re.sub(r"[\s().-]", "", value)
        if not re.fullmatch(r"\+?\d{8,15}", digits):
            raise serializers.ValidationError("Enter a valid WhatsApp number with country code, e.g. +923001234567.")
        return digits if digits.startswith("+") else f"+{digits}"

    def validate(self, attrs):
        fmt = attrs.get("interview_format", getattr(self.instance, "interview_format", InterviewFormat.ONSITE))
        number = attrs.get("interview_whatsapp_number", getattr(self.instance, "interview_whatsapp_number", ""))
        if fmt == InterviewFormat.VIDEO and not number:
            raise serializers.ValidationError(
                {"interview_whatsapp_number": "A WhatsApp number is required when the interview format is a video call."}
            )
        if fmt == InterviewFormat.ONSITE:
            # Only the WhatsApp number is irrelevant for on-site interviews; keep the field clean.
            attrs["interview_whatsapp_number"] = ""
            location = attrs.get("location", getattr(self.instance, "location", ""))
            if "interview_format" in self.initial_data and not (location or "").strip():
                raise serializers.ValidationError(
                    {"location": "Enter the location: it is the address candidates are invited to for on-site interviews."}
                )
        salary_min = attrs.get("salary_min", getattr(self.instance, "salary_min", None))
        salary_max = attrs.get("salary_max", getattr(self.instance, "salary_max", None))
        if salary_min is not None and salary_max is not None and salary_min > salary_max:
            raise serializers.ValidationError(
                {"salary_max": "Salary maximum must be greater than or equal to salary minimum."}
            )
        return attrs
