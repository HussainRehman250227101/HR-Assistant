"""Versioned, deterministic email templates (approved templates, FR-05/FR-10) and iCalendar attachments."""

from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.conf import settings

TEMPLATE_VERSION = "interview-email-v3"
REJECTION_TEMPLATE_VERSION = "rejection-email-v1"


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
        "mode": "WhatsApp video call" if (interview.mode == "VIDEO" and interview.contact_whatsapp and not interview.meeting_link)
        else interview.get_mode_display(),
        "meeting_link": interview.meeting_link,
        "whatsapp_number": interview.contact_whatsapp,
        "location": interview.location,
        "interviewer_name": interview.interviewer.get_full_name() or interview.interviewer.username,
        "interviewer_email": interview.interviewer.email,
        "rescheduling_contact": settings.INVITATION_RESCHEDULE_CONTACT,
        "organization_name": settings.SCREENING_ORGANIZATION_NAME,
    }


def _where_lines(d, interview):
    """(where line, one friendly sentence about how the interview works) for the interview format."""
    if interview.mode == "VIDEO" and d["whatsapp_number"] and not d["meeting_link"]:
        return (
            f"Where:     WhatsApp video call on {d['whatsapp_number']}",
            "This will be a WhatsApp video call. Please keep WhatsApp open and your phone handy a few minutes "
            "before the start time.",
        )
    if interview.mode == "VIDEO" and d["meeting_link"]:
        return f"Where:     {d['meeting_link']}", "This will be a video call - just click the link above at the start time."
    if interview.mode == "ONSITE" and d["location"]:
        return (
            f"Where:     {d['location']}",
            "This will be an on-site interview, so please come to the address above. Arriving 5-10 minutes early is perfect.",
        )
    where = d["meeting_link"] or d["whatsapp_number"] or d["location"] or "Phone call - we will call you on your registered number"
    return f"Where:     {where}", "We will connect with you at the time above."


def render(kind, interview, candidate):
    d = meeting_details(interview)
    full_name = (candidate.full_name or "").strip()
    first = full_name.split(" ")[0] if full_name else "there"
    org, role, contact = d["organization_name"], d["role_title"], d["rescheduling_contact"]
    sign_off = f"Warm regards,\nThe {org} Recruiting Team"
    if kind == "INTERVIEW_CANCELLATION":
        subject = f"About your {role} interview at {org}"
        body = (
            f"Hi {first},\n\n"
            f"I'm sorry to let you know that your interview for the {role} role, which was planned for "
            f"{d['date_time']} ({d['timezone']} time), has been cancelled.\n\n"
            "Thank you for your understanding. Our team will be in touch about what happens next. "
            f"If you have any questions in the meantime, please reach out to {contact} - we're happy to help.\n\n"
            f"{sign_off}"
        )
        return subject, body, d
    updated = kind == "INTERVIEW_RESCHEDULE"
    where_line, how = _where_lines(d, interview)
    subject = (f"New time for your {role} interview at {org}" if updated
               else f"You're invited! Interview for {role} at {org}")
    intro = (
        f"Quick update: we've had to move your interview for the {role} role at {org}. Sorry for any inconvenience - "
        "here are the new details."
        if updated else
        f"Thank you for taking the time to chat with us - we really enjoyed it! We'd love to invite you to an "
        f"interview for the {role} role at {org}."
    )
    body = (
        f"Hi {first},\n\n{intro}\n\n"
        "Here's everything you need:\n\n"
        f"When:      {d['date_time']} ({d['timezone']} time)\n"
        f"How long:  about {d['duration_minutes']} minutes\n"
        f"{where_line}\n"
        f"With:      {d['interviewer_name']} ({d['interviewer_email']})\n\n"
        f"{how}\n\n"
        "Does this time work for you? If it doesn't and you'd like to reschedule, or if there is anything that "
        f"would make the interview easier for you, just reply to this email or contact {contact} - "
        "we'll sort it out, no problem at all.\n\n"
        "A calendar invitation is attached so you can add the interview to your calendar in one click.\n\n"
        f"We're looking forward to meeting you!\n\n{sign_off}"
    )
    return subject, body, d


def render_rejection(candidate, requisition):
    """Friendly, specific rejection notice. It lists what was deleted; it never states HR's reason or scores."""
    full_name = (candidate.full_name or "").strip()
    first = full_name.split(" ")[0] if full_name else "there"
    org, role = settings.SCREENING_ORGANIZATION_NAME, requisition.title
    subject = f"Update on your application for {role} at {org}"
    body = (
        f"Hi {first},\n\n"
        f"Thank you so much for your interest in the {role} role at {org}, and for the time and effort you put into "
        "your application. We really appreciate it.\n\n"
        "After careful consideration, we have decided not to move forward with your application for this position. "
        "This was not an easy decision, and it takes nothing away from the skills and experience you shared with us.\n\n"
        "Your privacy matters to us, so we have also deleted your resume, your contact details, your screening answers "
        "and our evaluation notes from our HR system.\n\n"
        "We wish you every success in your job search, and we hope our paths cross again in the future.\n\n"
        f"Warm regards,\nThe {org} Recruiting Team"
    )
    return subject, body


def required_field_problems(log):
    """Guard against an HR edit removing a field the SRS requires in the invitation (FR-10)."""
    if log.kind in ("INTERVIEW_CANCELLATION", "REJECTION"):
        return []
    d = log.meeting_details
    checks = {
        "role title": d.get("role_title"),
        "date and time": d.get("date_time"),
        "time zone": d.get("timezone"),
        "meeting link, WhatsApp number or location": d.get("meeting_link") or d.get("whatsapp_number") or d.get("location"),
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
        f"LOCATION:{_escape(d.get('meeting_link') or ('WhatsApp video call ' + d['whatsapp_number'] if d.get('whatsapp_number') else '') or d.get('location') or 'Phone')}",
        f"ORGANIZER;CN={_escape(d.get('organization_name', ''))}:mailto:{settings.DEFAULT_FROM_EMAIL}",
        f"ATTENDEE;CN={_escape(interview.candidate.full_name or 'Candidate')};RSVP=TRUE:mailto:{log.recipient}",
        f"STATUS:{'CANCELLED' if cancelled else 'CONFIRMED'}", "END:VEVENT", "END:VCALENDAR",
    ]
    return "\r\n".join(lines) + "\r\n"
