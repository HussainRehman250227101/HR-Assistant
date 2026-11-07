"""Outbound destination validation. Development calling is restricted to configured prefixes (+92)."""

import re

from django.conf import settings


class DestinationNotAllowed(ValueError):
    pass


PAKISTAN_E164 = re.compile(r"^\+92\d{10}$")


def normalize_phone(raw):
    """Normalize common Pakistani formats (03xx..., 0092..., 92...) to E.164."""
    value = re.sub(r"[\s().-]", "", (raw or "").strip())
    if value.startswith("00"):
        value = "+" + value[2:]
    elif value.startswith("0") and len(value) == 11:
        value = "+92" + value[1:]
    elif value.startswith("92") and len(value) == 12:
        value = "+" + value
    return value


def validate_destination(raw):
    number = normalize_phone(raw)
    if not re.fullmatch(r"\+\d{8,15}", number):
        raise DestinationNotAllowed("The candidate phone number is not a valid international (E.164) number.")
    prefixes = settings.SCREENING_ALLOWED_DIAL_PREFIXES
    if not any(number.startswith(prefix) for prefix in prefixes):
        raise DestinationNotAllowed(
            f"Outbound screening calls are restricted to numbers starting with {', '.join(prefixes)}."
        )
    if number.startswith("+92") and not PAKISTAN_E164.fullmatch(number):
        raise DestinationNotAllowed("Pakistani numbers must have 10 digits after +92 (e.g. +923001234567).")
    return number


def mask_phone(number):
    number = normalize_phone(number)
    if len(number) <= 6:
        return "*" * len(number)
    return f"{number[:3]}{'*' * (len(number) - 7)}{number[-4:]}"
