from django.contrib import admin

from .models import AvailabilitySlot, Interview


@admin.register(AvailabilitySlot)
class AvailabilitySlotAdmin(admin.ModelAdmin):
    list_display = ("interviewer", "start", "end", "timezone", "source")
    list_filter = ("source",)


@admin.register(Interview)
class InterviewAdmin(admin.ModelAdmin):
    list_display = ("public_id", "candidate", "interviewer", "status", "confirmed_start", "timezone")
    list_filter = ("status", "mode")
    readonly_fields = [f.name for f in Interview._meta.fields]

    def has_add_permission(self, request):
        return False
