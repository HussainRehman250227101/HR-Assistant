"""Celery tasks for the candidates app (auto-discovered by config/celery.py)."""

import logging

from celery import shared_task
from django.conf import settings

from .services.decline import declined_awaiting_processing, safe_process_declined

logger = logging.getLogger(__name__)


@shared_task(name="candidates.tasks.process_declined_candidate", ignore_result=True)
def process_declined_candidate_task(candidate_id):
    return safe_process_declined(candidate_id)


@shared_task(name="candidates.tasks.process_declined_candidates", ignore_result=True)
def process_declined_candidates(limit=10):
    """Safety net run by Celery beat: send pending rejection notices and finish deletions the immediate task missed."""
    if not settings.REJECTION_AUTO_ENABLED:
        return {"enabled": False}
    handled = 0
    for candidate_id in list(declined_awaiting_processing().values_list("pk", flat=True)[:limit]):
        safe_process_declined(candidate_id)
        handled += 1
    return {"handled": handled}


def queue_declined_processing(candidate_id):
    """Ask the worker to process a declined candidate right after the decision. Best effort: beat is the fallback."""
    try:
        process_declined_candidate_task.delay(candidate_id)
    except Exception as exc:
        logger.warning("Could not queue declined-candidate processing. exception_type=%s", type(exc).__name__)
