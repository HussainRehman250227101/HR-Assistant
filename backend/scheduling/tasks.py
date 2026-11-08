"""Celery tasks for Agent 3 (auto-discovered by config/celery.py)."""

import logging

from celery import shared_task
from django.conf import settings

from .services.auto import candidates_awaiting_auto_schedule, safe_auto_schedule

logger = logging.getLogger(__name__)


@shared_task(name="scheduling.tasks.auto_schedule_candidate", ignore_result=True)
def auto_schedule_candidate_task(candidate_id):
    return safe_auto_schedule(candidate_id)


@shared_task(name="scheduling.tasks.auto_schedule_approved_candidates", ignore_result=True)
def auto_schedule_approved_candidates(limit=10):
    """Safety net run by Celery beat: pick up approved candidates the immediate task missed (e.g. worker was down)."""
    if not settings.INTERVIEW_AUTO_SCHEDULING_ENABLED:
        return {"enabled": False}
    handled = 0
    for candidate_id in list(candidates_awaiting_auto_schedule().values_list("pk", flat=True)[:limit]):
        safe_auto_schedule(candidate_id)  # records the reason for HR and never raises
        handled += 1
    return {"handled": handled}


def queue_auto_scheduling(candidate_id):
    """Ask the worker to schedule right after HR approves a screening. Best effort: beat is the fallback."""
    try:
        auto_schedule_candidate_task.delay(candidate_id)
    except Exception as exc:
        logger.warning("Could not queue automatic scheduling. exception_type=%s", type(exc).__name__)
