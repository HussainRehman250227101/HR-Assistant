"""Shared Django settings for all deployment environments."""

from pathlib import Path
import os

from config.env import BASE_DIR, env

env.read_env(BASE_DIR / ".env", overwrite=False)

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[]) # type:ignore
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[]) # type:ignore

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "accounts.apps.AccountsConfig",
    "requisitions.apps.RequisitionsConfig",
    "candidates.apps.CandidatesConfig",
    "llm.apps.LLMConfig",
    "scoring.apps.ScoringConfig",
    "reviews.apps.ReviewsConfig",
    "workflows.apps.WorkflowsConfig",
    "screening.apps.ScreeningConfig",
    "scheduling.apps.SchedulingConfig",
    "communications.apps.CommunicationsConfig",
    "dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [],
    "APP_DIRS": True,
    "OPTIONS": {"context_processors": [
        "django.template.context_processors.request",
        "django.contrib.auth.context_processors.auth",
        "django.contrib.messages.context_processors.messages",
    ]},
}]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": {
    "ENGINE": "django.db.backends.sqlite3",
    "NAME": Path(env("SQLITE_DB_PATH", default=str(BASE_DIR / "db.sqlite3"))), # type:ignore
    "CONN_MAX_AGE": 0,
}}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = env("LANGUAGE_CODE", default="en-us") # type:ignore
TIME_ZONE = env("TIME_ZONE", default="UTC") # type:ignore
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = False
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend") # type:ignore
EMAIL_HOST = env("EMAIL_HOST", default="") # type:ignore
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="") # type:ignore
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="") # type:ignore
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@example.invalid") # type:ignore
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "30/min", "user": "120/min"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": __import__("datetime").timedelta(days=10),
    "REFRESH_TOKEN_LIFETIME": __import__("datetime").timedelta(days=10),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "UPDATE_LAST_LOGIN": False,
}


# Azure OpenAI v1 client controls. Secrets remain in backend/.env only.
AZURE_OPENAI_ENDPOINT = env("AZURE_OPENAI_ENDPOINT", default="") # type:ignore
AZURE_OPENAI_API_KEY = env("AZURE_OPENAI_API_KEY", default="") # type:ignore
AZURE_OPENAI_CHAT_DEPLOYMENT = env("AZURE_OPENAI_CHAT_DEPLOYMENT", default="") # type:ignore
AZURE_OPENAI_TIMEOUT_SECONDS = env.int("AZURE_OPENAI_TIMEOUT_SECONDS", default=30)
AZURE_OPENAI_MAX_RETRIES = env.int("AZURE_OPENAI_MAX_RETRIES", default=2)
AZURE_OPENAI_REASONING_EFFORT = env("AZURE_OPENAI_REASONING_EFFORT", default="low") # type:ignore
AZURE_OPENAI_MAX_COMPLETION_TOKENS = env.int("AZURE_OPENAI_MAX_COMPLETION_TOKENS", default=2000)

# LangGraph SQLite checkpoints for durable local workflow state and human-review pauses.
LANGGRAPH_CHECKPOINT_DB_PATH = Path(env(
    "LANGGRAPH_CHECKPOINT_DB_PATH",
    default=str(BASE_DIR / "langgraph-checkpoints.sqlite3"),
))
LANGGRAPH_STRICT_MSGPACK = env.bool("LANGGRAPH_STRICT_MSGPACK", default=True)
if LANGGRAPH_STRICT_MSGPACK:
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

# Module 10: screening calls via ElevenLabs Conversational AI over its native Twilio integration.
TELEPHONY_PROVIDER = env("TELEPHONY_PROVIDER", default="twilio") # type:ignore
VOICE_AI_PROVIDER = env("VOICE_AI_PROVIDER", default="elevenlabs") # type:ignore
TWILIO_ACCOUNT_SID = env("TWILIO_ACCOUNT_SID", default="") # type:ignore
TWILIO_AUTH_TOKEN = env("TWILIO_AUTH_TOKEN", default="") # type:ignore
TWILIO_PHONE_NUMBER = env("TWILIO_PHONE_NUMBER", default="") # type:ignore
ELEVENLABS_API_BASE_URL = env("ELEVENLABS_API_BASE_URL", default="https://api.elevenlabs.io") # type:ignore
ELEVENLABS_API_KEY = env("ELEVENLABS_API_KEY", default="") # type:ignore
ELEVENLABS_AGENT_ID = env("ELEVENLABS_AGENT_ID", default="") # type:ignore
ELEVENLABS_AGENT_PHONE_NUMBER_ID = env("ELEVENLABS_AGENT_PHONE_NUMBER_ID", default="") # type:ignore
ELEVENLABS_WEBHOOK_SECRET = env("ELEVENLABS_WEBHOOK_SECRET", default="") # type:ignore
VOICE_PROVIDER_TIMEOUT_SECONDS = env.int("VOICE_PROVIDER_TIMEOUT_SECONDS", default=15)
SCREENING_ALLOWED_DIAL_PREFIXES = env.list("SCREENING_ALLOWED_DIAL_PREFIXES", default=["+92"]) # type:ignore
SCREENING_MAX_CALL_ATTEMPTS = env.int("SCREENING_MAX_CALL_ATTEMPTS", default=3)
SCREENING_RETRY_INTERVAL_MINUTES = env.int("SCREENING_RETRY_INTERVAL_MINUTES", default=120)
SCREENING_CALL_TIMEZONE = env("SCREENING_CALL_TIMEZONE", default="Asia/Karachi") # type:ignore
SCREENING_CALL_WINDOW_START_HOUR = env.int("SCREENING_CALL_WINDOW_START_HOUR", default=9)
SCREENING_CALL_WINDOW_END_HOUR = env.int("SCREENING_CALL_WINDOW_END_HOUR", default=19)
SCREENING_ORGANIZATION_NAME = env("SCREENING_ORGANIZATION_NAME", default="our company") # type:ignore
SCREENING_HUMAN_CONTACT = env("SCREENING_HUMAN_CONTACT", default="the recruiting team by email") # type:ignore

# Module 12: interview scheduling against the internal availability calendar.
SCHEDULING_MIN_NOTICE_HOURS = env.int("SCHEDULING_MIN_NOTICE_HOURS", default=12)
SCHEDULING_SLOT_STEP_MINUTES = env.int("SCHEDULING_SLOT_STEP_MINUTES", default=30)
SCHEDULING_MAX_PROPOSED_SLOTS = env.int("SCHEDULING_MAX_PROPOSED_SLOTS", default=6)

# Module 13: interview invitation emails (sent through EMAIL_BACKEND after explicit HR approval).
INVITATION_RESCHEDULE_CONTACT = env("INVITATION_RESCHEDULE_CONTACT", default=DEFAULT_FROM_EMAIL) # type:ignore
INVITATION_MESSAGE_ID_DOMAIN = env("INVITATION_MESSAGE_ID_DOMAIN", default="hr-assistant.local") # type:ignore

# Private resume upload limits and Django multipart request limits.
RESUME_MAX_FILE_SIZE_MB = env.int("RESUME_MAX_FILE_SIZE_MB", default=10)
RESUME_MAX_FILE_SIZE_BYTES = RESUME_MAX_FILE_SIZE_MB * 1024 * 1024
RESUME_MAX_BATCH_FILES = env.int("RESUME_MAX_BATCH_FILES", default=20)
RESUME_MAX_BATCH_TOTAL_MB = env.int("RESUME_MAX_BATCH_TOTAL_MB", default=50)
RESUME_MAX_BATCH_TOTAL_BYTES = RESUME_MAX_BATCH_TOTAL_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = RESUME_MAX_BATCH_TOTAL_BYTES + (1024 * 1024)
FILE_UPLOAD_PERMISSIONS = 0o640

LOG_LEVEL = env("LOG_LEVEL", default="INFO").upper() # type:ignore
LOGGING = {
    "version": 1, "disable_existing_loggers": False,
    "formatters": {"standard": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "standard"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {"django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False}},
}
