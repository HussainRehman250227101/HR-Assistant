"""Shared Django settings for all deployment environments."""

from pathlib import Path
import os

from django.core.exceptions import ImproperlyConfigured

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
    "audit.apps.AuditConfig",
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
# Blanks live provider keys during `manage.py test` so no test can make a real, billed call.
TEST_RUNNER = "config.test_runner.ProviderSafeTestRunner"
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
# Used only by django.core.mail.backends.filebased.EmailBackend: each email is saved as a readable .log file here.
EMAIL_FILE_PATH = env("EMAIL_FILE_PATH", default=str(BASE_DIR / "sent-emails")) # type:ignore
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
    # Defaults keep the existing 10-day local lifetimes; production.py shortens them (see JWT_* env vars).
    "ACCESS_TOKEN_LIFETIME": __import__("datetime").timedelta(minutes=env.int("JWT_ACCESS_TOKEN_MINUTES", default=60 * 24 * 10)),
    "REFRESH_TOKEN_LIFETIME": __import__("datetime").timedelta(minutes=env.int("JWT_REFRESH_TOKEN_MINUTES", default=60 * 24 * 10)),
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

# Automatic resume scoring (Celery). Beat enqueues a cycle every AUTO_SCORING_INTERVAL_SECONDS; the worker
# extracts pending resumes and starts the LangGraph scoring workflow for new ones. The human shortlist gate
# is unchanged. Run `celery -A config worker --pool=solo` and `celery -A config beat` (see README).
AUTO_SCORING_ENABLED = env.bool("AUTO_SCORING_ENABLED", default=True)
# Resumes extracted concurrently (the per-resume Azure name/location call dominates the time). 1 = sequential.
RESUME_EXTRACTION_WORKERS = env.int("RESUME_EXTRACTION_WORKERS", default=4)
AUTO_SCORING_INTERVAL_SECONDS = env.int("AUTO_SCORING_INTERVAL_SECONDS", default=120)
AUTO_SCORING_BATCH_LIMIT = env.int("AUTO_SCORING_BATCH_LIMIT", default=10)
if AUTO_SCORING_INTERVAL_SECONDS < 30 or AUTO_SCORING_BATCH_LIMIT < 1:
    raise ImproperlyConfigured("AUTO_SCORING_INTERVAL_SECONDS must be >= 30 and AUTO_SCORING_BATCH_LIMIT >= 1.")
# Default broker: a local SQLite file through SQLAlchemy (no extra service). Use Redis in production,
# e.g. CELERY_BROKER_URL=redis://localhost:6379/0 (and pip install redis).
CELERY_BROKER_URL = (
    env("CELERY_BROKER_URL", default="").strip()  # type:ignore
    or "sqla+sqlite:///" + (BASE_DIR / "celery-broker.sqlite3").as_posix()
)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_IGNORE_RESULT = True
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False  # keep Django's LOGGING (no resume text, contacts or keys in logs)
CELERY_BEAT_SCHEDULE_FILENAME = str(BASE_DIR / "celerybeat-schedule")
CELERY_BEAT_SCHEDULE = {
    "auto-score-new-resumes": {
        "task": "workflows.tasks.auto_score_new_resumes",
        "schedule": float(AUTO_SCORING_INTERVAL_SECONDS),
        # A cycle that waited longer than one interval in the queue is dropped; the next one covers it.
        "options": {"expires": AUTO_SCORING_INTERVAL_SECONDS},
    },
    "process-declined-candidates": {
        "task": "candidates.tasks.process_declined_candidates",
        "schedule": float(AUTO_SCORING_INTERVAL_SECONDS),
        "options": {"expires": AUTO_SCORING_INTERVAL_SECONDS},
    },
    "auto-schedule-approved-candidates": {
        "task": "scheduling.tasks.auto_schedule_approved_candidates",
        "schedule": float(AUTO_SCORING_INTERVAL_SECONDS),
        "options": {"expires": AUTO_SCORING_INTERVAL_SECONDS},
    },
}

# Module 16: AI voice screening mode.
#   "browser"   (default) - the ElevenLabs agent talks to the candidate in the browser over WebRTC; no phone
#                call is placed and no Twilio setting is needed (only ELEVENLABS_API_KEY + ELEVENLABS_AGENT_ID).
#   "telephony" - Module 10 outbound phone calls through ElevenLabs' native Twilio integration.
SCREENING_VOICE_MODE = env("SCREENING_VOICE_MODE", default="browser").strip().lower() # type:ignore
if SCREENING_VOICE_MODE not in ("browser", "telephony"):
    raise ImproperlyConfigured("SCREENING_VOICE_MODE must be 'browser' or 'telephony'.")
# A browser session that never connected (or was left open) is treated as abandoned after this long.
SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES = env.int("SCREENING_BROWSER_SESSION_TIMEOUT_MINUTES", default=15)

# Module 10: screening calls via ElevenLabs Conversational AI over its native Twilio integration
# (used only when SCREENING_VOICE_MODE=telephony; every Twilio setting is optional otherwise).
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
# Automatic scheduling (Agent 3): after HR approves a screening the agent matches the candidate's stated
# availability with an interviewer's calendar and emails the invitation without a separate send approval.
INTERVIEW_AUTO_SCHEDULING_ENABLED = env.bool("INTERVIEW_AUTO_SCHEDULING_ENABLED", default=True)
SCHEDULING_DEFAULT_TIMEZONE = env("SCHEDULING_DEFAULT_TIMEZONE", default="Asia/Karachi") # type:ignore
SCHEDULING_DEFAULT_DURATION_MINUTES = env.int("SCHEDULING_DEFAULT_DURATION_MINUTES", default=45)

# Declined candidates (user decision 2026-11-08): HR's DECLINE decision queues a friendly rejection email, then the
# candidate's resume and personal data are erased automatically (the name is kept so HR can tell who was declined).
REJECTION_AUTO_ENABLED = env.bool("REJECTION_AUTO_ENABLED", default=True)
REJECTION_MAX_EMAIL_ATTEMPTS = env.int("REJECTION_MAX_EMAIL_ATTEMPTS", default=5)

# Module 13: interview invitation emails (sent through EMAIL_BACKEND after explicit HR approval).
INVITATION_RESCHEDULE_CONTACT = env("INVITATION_RESCHEDULE_CONTACT", default=DEFAULT_FROM_EMAIL) # type:ignore
INVITATION_MESSAGE_ID_DOMAIN = env("INVITATION_MESSAGE_ID_DOMAIN", default="hr-assistant.local") # type:ignore

# Module 15: data retention for closed candidates (python manage.py apply_retention_policy).
CANDIDATE_RETENTION_DAYS = env.int("CANDIDATE_RETENTION_DAYS", default=365)

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
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        # httpx logs full request URLs at INFO (agent IDs, conversation IDs, Twilio account SIDs): keep them out of logs.
        "httpx": {"level": "WARNING"},
        "httpcore": {"level": "WARNING"},
    },
}
