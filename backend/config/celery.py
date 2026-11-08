"""Celery application for background work (automatic resume scoring).

Run from backend/ in two terminals (on Windows the worker needs --pool=solo, and beat must run separately):
    celery -A config worker --pool=solo --loglevel=info
    celery -A config beat --loglevel=info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.django.local")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
