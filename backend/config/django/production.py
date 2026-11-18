"""Production settings with explicit deployment safety checks."""

from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from config.env import env

DEBUG = False

if not SECRET_KEY or SECRET_KEY.startswith("django-insecure-change-this"):  # noqa: F405
    raise ImproperlyConfigured(
        "Set a unique SECRET_KEY environment variable before using production settings."
    )

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "Set ALLOWED_HOSTS to the production hostnames before using production settings."
    )

CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
if env.bool("USE_X_FORWARDED_PROTO", default=False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# WhiteNoise serves the admin static files and, when FRONTEND_DIST_DIR is set (Docker image), the built React
# app from the same origin as the API. Unknown non-API paths fall back to index.html (config/spa.py).
MIDDLEWARE = [*MIDDLEWARE]  # noqa: F405
MIDDLEWARE.insert(MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
                  "whitenoise.middleware.WhiteNoiseMiddleware")
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}
if FRONTEND_DIST_DIR:  # noqa: F405
    WHITENOISE_ROOT = FRONTEND_DIST_DIR  # noqa: F405

# The web server, Celery worker and Celery beat share one SQLite file; wait for locks instead of failing at once.
DATABASES["default"].setdefault("OPTIONS", {})["timeout"] = env.int("SQLITE_TIMEOUT_SECONDS", default=20)  # noqa: F405

# Short-lived access tokens in production; the SPA refreshes them automatically.
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_TOKEN_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_REFRESH_TOKEN_MINUTES", default=60 * 12)),
}

# Live candidate phone calls require a verified webhook so call results cannot be forged. Browser voice
# sessions (the default mode) fetch results from ElevenLabs on demand and need no webhook.
if SCREENING_VOICE_MODE == "telephony" and ELEVENLABS_API_KEY and not ELEVENLABS_WEBHOOK_SECRET:  # noqa: F405
    raise ImproperlyConfigured("Set ELEVENLABS_WEBHOOK_SECRET when ElevenLabs telephone calling is enabled in production.")

if EMAIL_BACKEND.endswith("console.EmailBackend"):  # noqa: F405
    import warnings

    warnings.warn("Production is using the console email backend; invitations will not be delivered.", stacklevel=1)
