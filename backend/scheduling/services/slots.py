"""Agent 3 availability engine: only genuinely free, mutually available slots are offered (SRS §8)."""

from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

from ..models import BOOKED_STATUSES, AvailabilitySlot, Interview


class SchedulingError(ValueError):
    pass


def get_zone(name):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise SchedulingError(f"Unknown time zone: {name}") from exc


def local_window_to_utc(date, start_time, end_time, tz_name):
    """Convert a wall-clock window in `tz_name` to an aware UTC (start, end) pair."""
    zone = get_zone(tz_name)
    start = datetime.combine(date, start_time, tzinfo=zone)
    end = datetime.combine(date, end_time, tzinfo=zone)
    if end <= start:
        raise SchedulingError("Each window must end after it starts.")
    return start.astimezone(dt_timezone.utc), end.astimezone(dt_timezone.utc)


def _ceil(moment, step_minutes):
    discard = timedelta(minutes=moment.minute % step_minutes, seconds=moment.second, microseconds=moment.microsecond)
    return moment if not discard else moment - discard + timedelta(minutes=step_minutes)


def busy_intervals(interviewer, exclude=None):
    qs = Interview.objects.filter(interviewer=interviewer, status__in=BOOKED_STATUSES, confirmed_start__isnull=False)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return list(qs.values_list("confirmed_start", "confirmed_end"))


def is_slot_free(interviewer, start, end, exclude=None):
    """True when the interviewer has an availability window covering the slot and no booked overlap."""
    covered = AvailabilitySlot.objects.filter(interviewer=interviewer, start__lte=start, end__gte=end).exists()
    clash = any(b_start < end and start < b_end for b_start, b_end in busy_intervals(interviewer, exclude))
    return covered and not clash


def compute_slots(interviewer, candidate_windows, duration_minutes, exclude=None, now=None, limit=None):
    """Intersect interviewer availability with candidate windows, minus booked interviews."""
    now = now or timezone.now()
    limit = limit or settings.SCHEDULING_MAX_PROPOSED_SLOTS
    step = settings.SCHEDULING_SLOT_STEP_MINUTES
    earliest = now + timedelta(hours=settings.SCHEDULING_MIN_NOTICE_HOURS)
    duration = timedelta(minutes=duration_minutes)
    busy = busy_intervals(interviewer, exclude)
    availability = AvailabilitySlot.objects.filter(interviewer=interviewer, end__gt=earliest).order_by("start")
    slots, seen = [], set()
    for window in availability:
        for c_start, c_end in candidate_windows:
            start = _ceil(max(window.start, c_start, earliest), step)
            end = min(window.end, c_end)
            while start + duration <= end:
                slot_end = start + duration
                if start not in seen and not any(b_start < slot_end and start < b_end for b_start, b_end in busy):
                    seen.add(start)
                    slots.append((start, slot_end))
                start += timedelta(minutes=step)
    slots.sort()
    return [{"start": s.isoformat(), "end": e.isoformat()} for s, e in slots[:limit]]
