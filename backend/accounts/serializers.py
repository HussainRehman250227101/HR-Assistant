from rest_framework import serializers

from .models import User


class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id", "username", "email", "first_name", "last_name",
            "full_name", "role", "department", "job_title", "is_superuser",
        )
        read_only_fields = fields

    @staticmethod
    def get_full_name(user: User) -> str:
        return user.get_full_name()
