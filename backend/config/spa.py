"""Serve the built React app's index.html for client-side routes (single-service deployment only)."""

from pathlib import Path

from django.conf import settings
from django.http import Http404, HttpResponse


def spa_index(request, *args, **kwargs):
    index = Path(settings.FRONTEND_DIST_DIR) / "index.html"
    if not settings.FRONTEND_DIST_DIR or not index.is_file():
        raise Http404
    response = HttpResponse(index.read_bytes(), content_type="text/html; charset=utf-8")
    # Always revalidate so a new deploy's hashed asset names are picked up.
    response["Cache-Control"] = "no-cache"
    return response
