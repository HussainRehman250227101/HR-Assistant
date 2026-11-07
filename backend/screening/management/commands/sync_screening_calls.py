from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from screening.models import CallAttemptStatus, ScreeningCallAttempt
from screening.services.calls import sync_attempt
from screening.services.voice import VoiceConfigurationError, VoiceProviderError


class Command(BaseCommand):
    help = "Poll Twilio/ElevenLabs for in-progress screening calls and conclude finished ones (webhook fallback)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--min-age-seconds", type=int, default=30)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(seconds=options["min_age_seconds"])
        attempts = ScreeningCallAttempt.objects.select_related("screening__candidate", "screening__requisition").filter(
            status=CallAttemptStatus.IN_PROGRESS, started_at__lte=cutoff,
        ).order_by("started_at")[: options["limit"]]
        concluded = failed = 0
        for attempt in attempts:
            try:
                if sync_attempt(attempt).status != CallAttemptStatus.IN_PROGRESS:
                    concluded += 1
            except (VoiceConfigurationError, VoiceProviderError) as exc:
                failed += 1
                self.stderr.write(f"Attempt {attempt.public_id}: {type(exc).__name__}")
        self.stdout.write(self.style.SUCCESS(f"Concluded {concluded} call(s); {failed} sync error(s)."))
