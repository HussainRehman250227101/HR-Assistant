"""Demo: email the candidate a link to the AI browser voice screening once HR approves them (gate 1 stays human).

The link carries a signed, expiring token (no login). Opening it shows the disclosure/consent screen; the session
itself is the existing browser voice flow (`services/browser.py`). The candidate never sees results.
"""

import logging

from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage

from candidates.models import CandidateEvent, CandidateStatus
from candidates.services.status import record_event
from ..models import ACTIVE_SCREENING_STATUSES, Screening, ScreeningChannel
from .calls import ScreeningError, create_screening

logger = logging.getLogger(__name__)
EVENT = CandidateEvent.EventType
SALT = "screening-invite"


def make_token(screening):
    return signing.dumps(str(screening.public_id), salt=SALT)


def screening_from_token(token):
    """Return the screening for a valid, unexpired token, else None."""
    try:
        public_id = signing.loads(token, salt=SALT, max_age=settings.SCREENING_INVITE_MAX_AGE_DAYS * 86400)
    except signing.BadSignature:
        return None
    return Screening.objects.select_related("candidate", "requisition", "created_by").filter(public_id=public_id).first()


def invite_url(screening):
    return f"{settings.FRONTEND_BASE_URL.rstrip('/')}/screening-invite/{make_token(screening)}"


def _email(screening):
    candidate, org = screening.candidate, settings.SCREENING_ORGANIZATION_NAME
    name = (candidate.full_name or "").strip().split(" ")[0] or "there"
    role = screening.requisition.title
    lines = [
        f"Hello {name},",
        "",
        f"Thank you for applying for the {role} role at {org}. We would like to hold a short screening interview with you.",
        "",
        "Start whenever you are ready (about 10 minutes, on a computer with a microphone):",
        invite_url(screening),
        "",
        "Please note:",
        "- You will speak with an AI voice agent, not a person. No phone call is made.",
        "- Your voice is processed by our voice-AI provider and a transcript is kept for our HR team to review.",
        "- You will be asked to confirm your consent before the interview starts, and you can stop at any time.",
        "- The AI does not make hiring decisions; a member of our team reviews every interview.",
        "",
        f"The link is valid for {settings.SCREENING_INVITE_MAX_AGE_DAYS} days.",
        "",
        "Kind regards,",
        f"{org} HR team",
    ]
    body = chr(10).join(lines)
    return EmailMessage(f"Your screening interview for {role} at {org}", body, settings.DEFAULT_FROM_EMAIL, [candidate.email])


def send_screening_invite(screening, actor):
    """Email the link. Returns True if the email backend accepted it; failures are recorded, never raised."""
    candidate = screening.candidate
    try:
        _email(screening).send(fail_silently=False)
    except Exception as exc:  # the message may hold an address: log only the type
        logger.warning("Screening invitation email failed. screening=%s error=%s", screening.public_id, type(exc).__name__)
        record_event(candidate, actor, EVENT.SCREENING_INVITE_FAILED, screening_id=str(screening.public_id),
                     error=type(exc).__name__)
        return False
    record_event(candidate, actor, EVENT.SCREENING_INVITE_SENT, screening_id=str(screening.public_id))
    return True


def invite_after_approval(candidate, actor):
    """Create the browser screening and email the link. Never raises: HR can still screen the candidate manually."""
    if not settings.SCREENING_INVITE_EMAIL_ENABLED or settings.SCREENING_VOICE_MODE != "browser":
        return None
    try:
        if candidate.current_status != CandidateStatus.APPROVED_FOR_SCREENING:
            return None
        if not candidate.email:
            record_event(candidate, actor, EVENT.SCREENING_INVITE_FAILED, error="NO_EMAIL")
            return None
        screening = create_screening(candidate, actor, ScreeningChannel.BROWSER_VOICE)
    except ScreeningError as exc:
        record_event(candidate, actor, EVENT.SCREENING_INVITE_FAILED, error=str(exc)[:200])
        return None
    except Exception as exc:
        logger.warning("Screening invitation setup failed. candidate=%s error=%s", candidate.public_id, type(exc).__name__)
        return None
    send_screening_invite(screening, actor)
    return screening


def resend_invite(screening, actor):
    if screening.channel != ScreeningChannel.BROWSER_VOICE or screening.status not in ACTIVE_SCREENING_STATUSES:
        raise ScreeningError("Only an active browser screening can be re-sent.")
    if not screening.candidate.email:
        raise ScreeningError("The candidate has no email address.")
    return send_screening_invite(screening, actor)
