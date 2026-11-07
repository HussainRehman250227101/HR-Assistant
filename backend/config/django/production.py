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

# Short-lived access tokens in production; the SPA refreshes them automatically.
SIMPLE_JWT = {
    **SIMPLE_JWT,  # noqa: F405
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_TOKEN_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_REFRESH_TOKEN_MINUTES", default=60 * 12)),
}

# Live candidate calls require a verified webhook so call results cannot be forged.
if ELEVENLABS_API_KEY and not ELEVENLABS_WEBHOOK_SECRET:  # noqa: F405
    raise ImproperlyConfigured("Set ELEVENLABS_WEBHOOK_SECRET when ElevenLabs calling is enabled in production.")

if EMAIL_BACKEND.endswith("console.EmailBackend"):  # noqa: F405
    import warnings

    warnings.warn("Production is using the console email backend; invitations will not be delivered.", stacklevel=1)
