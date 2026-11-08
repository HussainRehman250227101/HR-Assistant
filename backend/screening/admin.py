from django.contrib import admin

from .models import Screening, ScreeningCallAttempt


class CallAttemptInline(admin.TabularInline):
    model = ScreeningCallAttempt
    extra = 0
    fields = ("attempt_number", "provider", "status", "outcome", "destination_masked", "telephony_status", "started_at", "ended_at")
    readonly_fields = fields
    can_delete = False


@admin.register(Screening)
class ScreeningAdmin(admin.ModelAdmin):
    list_display = ("public_id", "candidate", "channel", "status", "call_status", "consent_status", "attempt_count", "created_at")
    list_filter = ("channel", "status", "call_status")
    readonly_fields = [f.name for f in Screening._meta.fields]
    inlines = [CallAttemptInline]

    def has_add_permission(self, request):
        return False
