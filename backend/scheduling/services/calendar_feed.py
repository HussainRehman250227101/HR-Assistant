"""Calendar sync for interviewers: a private iCalendar (.ics) subscription feed of their interviews.

Works with Google Calendar ("From URL"), Microsoft Outlook ("Subscribe from web") and Apple Calendar without any
OAuth app or credentials. It is one-way (this app -> their calendar): interviews appear, move or disappear in
their calendar a few hours after they change here (the calendar app decides how often it refreshes).
The feed URL holds a secret token that can be regenerated. It contains no candidate contact details or resume
content: the candidate's name, role, time, place and a link to the candidate page.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from communications.templates_text import _escape, _ics_time
from ..models import Interview, InterviewStatus

FEED_STATUSES = (InterviewStatus.SLOT_CONFIRMED, InterviewStatus.SCHEDULED, InterviewStatus.COMPLETED)


def get_or_create_token(user, rotate=False):
    if rotate or not user.calendar_token:
        user.calendar_token = secrets.token_urlsafe(32)
        user.save(update_fields=("calendar_token",))
    return user.calendar_token


def feed_path(token):
    return f"/api/v1/scheduling/calendar/{token}/interviews.ics"


def feed_url(token):
    return settings.PUBLIC_BACKEND_URL.rstrip("/") + feed_path(token)


def _fold(line):
    """RFC 5545: lines longer than 75 octets are folded with CRLF + space."""
    raw, out = line.encode("utf-8"), []
    while len(raw) > 75:
        cut = 75
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # do not split a multi-byte character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


def build_feed(user, now=None):
    now = now or timezone.now()
    interviews = Interview.objects.select_related("candidate", "requisition").filter(
        interviewer=user, status__in=FEED_STATUSES, confirmed_start__isnull=False,
        confirmed_start__gte=now - timedelta(days=30),
    ).order_by("confirmed_start")
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HR Assistant//Interviewer Feed//EN", "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape('HR interviews - ' + (user.get_full_name() or user.username))}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H",
    ]
    base = settings.FRONTEND_BASE_URL.rstrip("/")
    for i in interviews:
        name = (i.candidate.full_name or "").strip() or "Candidate"
        where = i.meeting_link or (f"WhatsApp video call {i.contact_whatsapp}" if i.contact_whatsapp else "") or i.location or i.get_mode_display()
        lines += [
            "BEGIN:VEVENT", f"UID:feed-{i.public_id}@hr-assistant", f"SEQUENCE:{i.sequence}", f"DTSTAMP:{_ics_time(i.updated_at)}",
            f"DTSTART:{_ics_time(i.confirmed_start)}", f"DTEND:{_ics_time(i.confirmed_end)}",
            f"SUMMARY:{_escape(f'Interview: {name} - {i.requisition.title}')}", f"LOCATION:{_escape(where)}",
            f"DESCRIPTION:{_escape(f'Candidate details and CV: {base}/candidates/{i.candidate.public_id}')}",
            "STATUS:CONFIRMED", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
