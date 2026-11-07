"""Versioned, deterministic email templates (approved templates, FR-05/FR-10) and iCalendar attachments."""

from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings

TEMPLATE_VERSION = "interview-email-v1"


def _when(interview):
    local = interview.confirmed_start.astimezone(ZoneInfo(interview.timezone))
    return local.strftime("%A, %d %B %Y at %H:%M"), interview.timezone


def meeting_details(interview):
    date_text, tz = _when(interview) if interview.confirmed_start else ("", interview.timezone)
    return {
        "role_title": interview.requisition.title,
        "date_time": date_text,
        "timezone": tz,
        "duration_minutes": interview.duration_minutes,
        "mode": interview.get_mode_display(),
        "meeting_link": interview.meeting_link,
        "location": interview.location,
        "interviewer_name": interview.interviewer.get_full_name() or interview.interviewer.username,
        "interviewer_email": interview.interviewer.email,
        "rescheduling_contact": settings.INVITATION_RESCHEDULE_CONTACT,
        "organization_name": settings.SCREENING_ORGANIZATION_NAME,
    }


def render(kind, interview, candidate):
    d = meeting_details(interview)
    name = candidate.full_name or "Candidate"
    where = d["meeting_link"] or d["location"] or "Phone call - the interviewer will call you on your registered number"
    if kind == "INTERVIEW_CANCELLATION":
        subject = f"Interview cancelled: {d['role_title']} at {d['organization_name']}"
        body = (
            f"Dear {name},\n\nWe are sorry to let you know that your interview for the {d['role_title']} role, "
            f"previously scheduled for {d['date_time']} ({d['timezone']}), has been cancelled.\n\n"
            f"The recruiting team will contact you about next steps. For questions, contact {d['rescheduling_contact']}.\n\n"
            f"Kind regards,\n{d['organization_name']} Recruiting Team"
        )
        return subject, body, d
    updated = kind == "INTERVIEW_RESCHEDULE"
    subject = f"{'Updated interview time' if updated else 'Interview invitation'}: {d['role_title']} at {d['organization_name']}"
    body = (
        f"Dear {name},\n\n"
        + ("Your interview has been rescheduled. The new details are below.\n\n" if updated else
           f"Thank you for your interest in the {d['role_title']} role. We are pleased to invite you to an interview.\n\n")
        + f"Role: {d['role_title']}\n"
        f"Date and time: {d['date_time']}\n"
        f"Time zone: {d['timezone']}\n"
        f"Duration: {d['duration_minutes']} minutes\n"
        f"Format: {d['mode']}\n"
        f"Meeting link / location: {where}\n"
        f"Interviewer: {d['interviewer_name']} ({d['interviewer_email']})\n\n"
        f"If you need to reschedule or need any accommodation, please contact {d['rescheduling_contact']} "
        "as early as possible.\n\nA calendar invitation is attached.\n\n"
        f"Kind regards,\n{d['organization_name']} Recruiting Team"
    )
    return subject, body, d


def required_field_problems(log):
    """Guard against an HR edit removing a field the SRS requires in the invitation (FR-10)."""
    if log.kind == "INTERVIEW_CANCELLATION":
        return []
    d = log.meeting_details
    checks = {
        "role title": d.get("role_title"),
        "date and time": d.get("date_time"),
        "time zone": d.get("timezone"),
        "meeting link or location": d.get("meeting_link") or d.get("location"),
        "rescheduling contact": d.get("rescheduling_contact"),
    }
    return [label for label, value in checks.items() if value and str(value) not in log.body]


def _ics_time(value):
    return value.astimezone(dt_timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _escape(text):
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def build_ics(interview, log, now):
    cancelled = log.kind == "INTERVIEW_CANCELLATION"
    d = log.meeting_details
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//HR Assistant//Interview Scheduling//EN",
        f"METHOD:{'CANCEL' if cancelled else 'REQUEST'}", "BEGIN:VEVENT",
        f"UID:{interview.public_id}@hr-assistant", f"SEQUENCE:{log.sequence}", f"DTSTAMP:{_ics_time(now)}",
        f"DTSTART:{_ics_time(interview.confirmed_start)}", f"DTEND:{_ics_time(interview.confirmed_end)}",
        f"SUMMARY:{_escape('Interview - ' + d.get('role_title', ''))}",
        f"LOCATION:{_escape(d.get('meeting_link') or d.get('location') or 'Phone')}",
        f"ORGANIZER;CN={_escape(d.get('organization_name', ''))}:mailto:{settings.DEFAULT_FROM_EMAIL}",
        f"ATTENDEE;CN={_escape(interview.candidate.full_name or 'Candidate')};RSVP=TRUE:mailto:{log.recipient}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}", "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
