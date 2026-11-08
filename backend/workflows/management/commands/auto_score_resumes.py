"""Run one automatic scoring cycle now, without Celery (same code the scheduled task runs)."""

from django.core.management.base import BaseCommand, CommandError

from workflows.auto import run_auto_scoring_cycle


class Command(BaseCommand):
    help = "Extract pending resumes and score new ones once (makes live Azure OpenAI calls)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=None)
        parser.add_argument(
            "--retry-failed", action="store_true",
            help="Also re-score resumes whose earlier scoring runs all failed (e.g. after fixing Azure settings).",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        if limit is not None and not 1 <= limit <= 500:
            raise CommandError("--limit must be between 1 and 500.")
        summary = run_auto_scoring_cycle(limit=limit, retry_failed=options["retry_failed"])
        self.stdout.write(self.style.SUCCESS(
            f"Extracted {summary['extracted']}, released {summary['released_stale']} stale runs, "
            f"started {summary['started']} scoring runs: {summary['scored']} scored, {summary['failed']} failed."
        ))
