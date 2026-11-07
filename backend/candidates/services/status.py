"""Shared helpers so every candidate status change writes an audit event (FR-12, FR-14)."""

from ..models import CandidateEvent


def record_event(candidate, actor, event_type, **details):
    return CandidateEvent.objects.create(candidate=candidate, actor=actor, event_type=event_type, details=details)


def change_candidate_status(candidate, to_status, actor, reason, **details):
    previous = candidate.current_status
    if previous == to_status:
        return previous
    candidate.current_status = to_status
    candidate.save(update_fields=("current_status", "updated_at"))
    record_event(
        candidate, actor, CandidateEvent.EventType.STATUS_CHANGED,
        **{"from": previous, "to": to_status, "reason": reason, **details},
    )
    return previous
