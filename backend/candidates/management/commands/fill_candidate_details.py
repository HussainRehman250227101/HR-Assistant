"""Fill missing candidate name/contact details from already-extracted resumes (one-off backfill)."""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from candidates.models import Candidate, CandidateStatus, ResumeProcessingStatus
from candidates.services.contact_details import fill_candidate_details_from_resume


class Command(BaseCommand):
    help = "Read name, email, phone, location and LinkedIn URL from extracted resumes into empty candidate fields (uses Azure for name/location)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 1000:
            raise CommandError("--limit must be between 1 and 1000.")
        missing = Q(full_name="") | Q(email__isnull=True) | Q(email="") | Q(phone="") | Q(location="") | Q(linkedin_url="")
        candidates = (
            Candidate.objects.filter(personal_data_erased_at__isnull=True)
            .exclude(current_status=CandidateStatus.CLOSED)
            .filter(missing | Q(identity_review_required=True))
            .order_by("created_at")[:limit]
        )
        updated = 0
        for candidate in candidates:
            resume = candidate.resume_documents.filter(
                processing_status=ResumeProcessingStatus.COMPLETED
            ).order_by("-processed_at", "-created_at").first()
            if resume and fill_candidate_details_from_resume(resume):
                updated += 1
        self.stdout.write(self.style.SUCCESS(f"Filled details for {updated} candidate(s)."))
