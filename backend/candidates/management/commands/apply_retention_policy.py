from django.conf import settings
from django.core.management.base import BaseCommand

from candidates.services.privacy import erase_personal_data, expired_candidates


class Command(BaseCommand):
    help = "Erase personal data of candidates closed longer than CANDIDATE_RETENTION_DAYS (use --dry-run first)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        candidates = list(expired_candidates())
        self.stdout.write(f"{len(candidates)} closed candidate(s) older than {settings.CANDIDATE_RETENTION_DAYS} days.")
        if options["dry_run"]:
            for candidate in candidates:
                self.stdout.write(f"  would erase {candidate.public_id}")
            return
        for candidate in candidates:
            erase_personal_data(candidate, None, f"Retention period of {settings.CANDIDATE_RETENTION_DAYS} days expired")
        self.stdout.write(self.style.SUCCESS(f"Erased personal data for {len(candidates)} candidate(s)."))
