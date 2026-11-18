#!/bin/bash
# Railway entrypoint: migrate, then run the web server, the Celery worker and Celery beat in one container.
# If any of the three exits, the container exits so Railway restarts it.
set -euo pipefail
cd /app/backend

# Persistent data goes on the Railway volume (attach one; mount path e.g. /data).
DATA_DIR="${RAILWAY_VOLUME_MOUNT_PATH:-}"
if [ -z "$DATA_DIR" ]; then
  echo "WARNING: no Railway volume attached. The database and uploaded resumes are lost on every redeploy." >&2
  DATA_DIR=/app/backend/data
fi
mkdir -p "$DATA_DIR/media"

export SQLITE_DB_PATH="${SQLITE_DB_PATH:-$DATA_DIR/db.sqlite3}"
export LANGGRAPH_CHECKPOINT_DB_PATH="${LANGGRAPH_CHECKPOINT_DB_PATH:-$DATA_DIR/langgraph-checkpoints.sqlite3}"
export MEDIA_ROOT="${MEDIA_ROOT:-$DATA_DIR/media}"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-sqla+sqlite:///$DATA_DIR/celery-broker.sqlite3}"
export CELERY_BEAT_SCHEDULE_FILENAME="${CELERY_BEAT_SCHEDULE_FILENAME:-$DATA_DIR/celerybeat-schedule}"

# Defaults derived from the Railway domain; set these variables yourself to use a custom domain.
if [ -n "${RAILWAY_PUBLIC_DOMAIN:-}" ]; then
  PUBLIC_URL="https://$RAILWAY_PUBLIC_DOMAIN"
  export ALLOWED_HOSTS="${ALLOWED_HOSTS:-$RAILWAY_PUBLIC_DOMAIN}"
  export CSRF_TRUSTED_ORIGINS="${CSRF_TRUSTED_ORIGINS:-$PUBLIC_URL}"
  export FRONTEND_BASE_URL="${FRONTEND_BASE_URL:-$PUBLIC_URL}"
  export PUBLIC_BACKEND_URL="${PUBLIC_BACKEND_URL:-$PUBLIC_URL}"
fi
# Railway terminates TLS at its proxy; without this, SECURE_SSL_REDIRECT loops forever.
export USE_X_FORWARDED_PROTO="${USE_X_FORWARDED_PROTO:-True}"

python manage.py migrate --noinput
python manage.py collectstatic --noinput -v 0

# Optional first admin: set DJANGO_SUPERUSER_USERNAME, DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD.
if [ -n "${DJANGO_SUPERUSER_USERNAME:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py createsuperuser --noinput >/dev/null 2>&1 \
    && echo "Created superuser ${DJANGO_SUPERUSER_USERNAME}." \
    || echo "Superuser not created (it probably exists already)."
fi

celery -A config worker --loglevel=info --concurrency="${CELERY_CONCURRENCY:-2}" &
celery -A config beat --loglevel=info --schedule="$CELERY_BEAT_SCHEDULE_FILENAME" &
# No access log: the calendar feed URL contains a secret token.
gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads 4 \
  --timeout 180 &

trap 'kill -TERM $(jobs -p) 2>/dev/null; wait' TERM INT
set +e
wait -n
status=$?
echo "A process exited (status $status); stopping the container so Railway restarts it." >&2
kill -TERM $(jobs -p) 2>/dev/null
wait
exit "$status"
