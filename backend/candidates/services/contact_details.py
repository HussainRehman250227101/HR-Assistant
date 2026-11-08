"""Fill a candidate's name and contact details from their own resume (SRS §4.1: "normalize relevant candidate details").

Runs right after successful text extraction and before scoring, so HR never types these details in and the
scoring agent can redact them before its Azure call.

- Email, phone and LinkedIn URL: local pattern matching, no AI call. The top of the resume is searched first;
  further down, a value is used only if it is the only one in the document (so a referee's details are not taken).
- Name and location: Azure OpenAI reads only the top of the resume. A value is kept only if it appears verbatim
  in the resume (SRS §14: never invent extracted content). Without Azure, a local rule finds the name and the
  location is left empty.
- Only empty fields are filled. Values a recruiter entered are never overwritten.
- Values are never logged. The audit event lists field names only (SRS §12).
"""

import logging
import re

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, validate_email
from django.db import transaction
from pydantic import BaseModel, Field

from llm.prompts import build_messages
from llm.services import get_llm_provider
from ..models import Candidate, CandidateEvent, CandidateStatus

logger = logging.getLogger(__name__)

HEADER_CHARS = 2500
EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
PHONE_RE = re.compile(r"(?<![\w+])\+?\d[\d().\s-]{7,}\d(?!\w)")
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/[A-Za-z0-9_%-]+/?", re.IGNORECASE)
NAME_TOKEN_RE = re.compile(r"^[^\W\d_]+(?:[.'’-][^\W\d_]+)*\.?$")
NOT_A_NAME = {
    "resume", "résumé", "curriculum", "vitae", "cv", "profile", "summary", "contact", "objective", "experience",
    "education", "skills", "projects", "references", "personal", "details", "information", "career", "professional",
    "engineer", "developer", "manager", "analyst", "designer", "consultant", "intern", "specialist", "address",
}

IDENTITY_PROMPT = """You read the top of a candidate's resume for a recruiting system.
Return the candidate's own full name exactly as written, and the candidate's current location as written
(city and/or country only, no street address). Return null for anything not explicitly stated.
Never guess, infer, translate or complete a value. Do not return names of referees, employers, schools or other people."""


class ResumeIdentity(BaseModel):
    full_name: str | None = Field(description="The candidate's own full name, copied exactly, or null.")
    location: str | None = Field(description="The candidate's current city and/or country, copied exactly, or null.")


def _squash(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _appears_in(value, text):
    return bool(value) and _squash(value).casefold() in _squash(text).casefold()


def _tidy_name(value):
    value = _squash(value)
    return value.title() if value.isupper() else value


def _looks_like_name(value):
    value = _squash(value)
    if not value or len(value) > 120 or "@" in value:
        return False
    tokens = value.replace(",", " ").split()
    if not 2 <= len(tokens) <= 6:
        return False
    return all(NAME_TOKEN_RE.match(t) for t in tokens) and not any(t.casefold().strip(".") in NOT_A_NAME for t in tokens)


def _pick(pattern, text, normalize):
    """First valid match near the top; elsewhere only an unambiguous single value."""
    for match in pattern.finditer(text[:HEADER_CHARS]):
        value = normalize(match.group(0))
        if value:
            return value
    values = {v for v in (normalize(m.group(0)) for m in pattern.finditer(text)) if v}
    return values.pop() if len(values) == 1 else None


def _normalize_email(raw):
    value = raw.strip().strip(".").lower()
    try:
        validate_email(value)
    except ValidationError:
        return None
    return value


def _normalize_phone(raw):
    digits = re.sub(r"\D", "", raw)
    if not 9 <= len(digits) <= 15:
        return None
    return ("+" if raw.strip().startswith("+") else "") + digits


def _normalize_linkedin(raw):
    value = raw.strip().rstrip("/")
    if not value.lower().startswith("http"):
        value = f"https://{value}"
    try:
        URLValidator(schemes=["https", "http"])(value)
    except ValidationError:
        return None
    return value[:500]


def heuristic_name(text):
    for line in [l for l in (text or "").splitlines() if l.strip()][:8]:
        if len(line.strip()) <= 60 and _looks_like_name(line):
            return _tidy_name(line)
    return None


def detect_details(text, provider=None):
    """Return ({field: value}, name_source). Values are verbatim from the resume (normalised formatting only)."""
    details = {
        "email": _pick(EMAIL_RE, text, _normalize_email),
        "phone": _pick(PHONE_RE, text, _normalize_phone),
        "linkedin_url": _pick(LINKEDIN_RE, text, _normalize_linkedin),
    }
    name_source = None
    provider = provider or get_llm_provider()
    if getattr(provider, "is_configured", False):
        header = text[:HEADER_CHARS]
        try:
            identity = provider.generate_structured(
                messages=build_messages(IDENTITY_PROMPT, f"Top of the resume:\n\n{header}"),
                response_model=ResumeIdentity,
                max_completion_tokens=1500,
            )
            if identity.full_name and _appears_in(identity.full_name, header) and _looks_like_name(identity.full_name):
                details["full_name"] = _tidy_name(identity.full_name)
                name_source = "ai"
            location = _squash(identity.location or "")
            if location and len(location) <= 160 and "@" not in location and _appears_in(location, header):
                details["location"] = location
        except Exception as exc:  # the AI is optional here; never block extraction
            logger.warning("Resume identity detection by AI failed. exception_type=%s", type(exc).__name__)
    if not details.get("full_name"):
        details["full_name"] = heuristic_name(text)
        name_source = "heuristic" if details["full_name"] else None
    return {k: v for k, v in details.items() if v}, name_source


def fill_candidate_details_from_resume(document, actor=None, provider=None):
    """Fill empty candidate fields from this resume. Returns the list of field names filled."""
    candidate = Candidate.objects.get(pk=document.candidate_id)
    if candidate.personal_data_erased_at or candidate.current_status == CandidateStatus.CLOSED:
        return []
    text = document.extracted_text or ""
    if not text.strip():
        return []
    details, name_source = detect_details(text, provider=provider)

    with transaction.atomic():
        locked = Candidate.objects.select_for_update().get(pk=candidate.pk)
        filled, duplicate_email = [], False
        for field, value in details.items():
            if getattr(locked, field):
                continue
            if field == "email" and Candidate.objects.filter(
                requisition_id=locked.requisition_id, email__iexact=value
            ).exclude(pk=locked.pk).exists():
                duplicate_email = True  # likely the same person applied twice; leave it for HR
                continue
            setattr(locked, field, value)
            filled.append(field)
        clears_review = locked.identity_review_required and bool(locked.email or locked.phone) and not duplicate_email
        if not filled and not clears_review and not duplicate_email:
            return []
        if clears_review:
            locked.identity_review_required = False
        locked.auto_filled_fields = sorted(set(locked.auto_filled_fields or []) | set(filled))
        locked.save(update_fields=(*filled, "identity_review_required", "auto_filled_fields", "updated_at"))
        CandidateEvent.objects.create(
            candidate=locked, actor=actor, event_type=CandidateEvent.EventType.CANDIDATE_DETAILS_FROM_RESUME,
            details={
                "resume_document_id": str(document.public_id),
                "fields": filled,
                "name_source": name_source if "full_name" in filled else None,
                "possible_duplicate_email": duplicate_email,
                "contact_details_missing": not (locked.email or locked.phone),
            },
        )
    return filled
