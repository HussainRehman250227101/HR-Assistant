"""Celery tasks for the workflows app (auto-discovered by config/celery.py)."""

from celery import shared_task
from django.conf import settings

from .auto import run_auto_scoring_cycle

AUTO_SCORE_TASK_NAME = "workflows.tasks.auto_score_new_resumes"


@shared_task(name=AUTO_SCORE_TASK_NAME, ignore_result=True)
def auto_score_new_resumes():
    """Scheduled by Celery beat every AUTO_SCORING_INTERVAL_SECONDS (default 120)."""
    if not settings.AUTO_SCORING_ENABLED:
        return {"enabled": False}
    return run_auto_scoring_cycle()
