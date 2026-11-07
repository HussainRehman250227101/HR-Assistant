"""SRS §11 AuditEvent for non-candidate changes (requisitions, rubrics, privacy actions). Append-only."""

import uuid

from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="audit_events")
    action = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=60, db_index=True)
    entity_id = models.CharField(max_length=64, db_index=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.action} {self.entity_type}:{self.entity_id}"


def log_audit(actor, action, entity_type, entity_id, **details):
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action, entity_type=entity_type, entity_id=str(entity_id), details=details,
    )
