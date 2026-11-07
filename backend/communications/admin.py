from django.contrib import admin

from .models import CommunicationLog


@admin.register(CommunicationLog)
class CommunicationLogAdmin(admin.ModelAdmin):
    list_display = ("public_id", "candidate", "kind", "approval_status", "send_status", "sent_at")
    list_filter = ("kind", "approval_status", "send_status")
    readonly_fields = [f.name for f in CommunicationLog._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
