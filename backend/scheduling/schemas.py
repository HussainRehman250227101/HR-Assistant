"""Pydantic schema for reading the availability a candidate stated in the screening (Agent 3)."""

from pydantic import BaseModel, Field


class AvailabilityWindowOut(BaseModel):
    date: str = Field(description="Calendar date as YYYY-MM-DD, resolved from the call date and weekday.")
    start_time: str = Field(description="Local start time, 24-hour HH:MM.")
    end_time: str = Field(description="Local end time, 24-hour HH:MM; must be after start_time.")


class CandidateAvailabilityOut(BaseModel):
    timezone: str = Field(
        description="IANA time zone name (for example Asia/Karachi) only if the candidate named a time zone or a "
                    "city/country that maps to exactly one zone; otherwise an empty string."
    )
    windows: list[AvailabilityWindowOut] = Field(
        description="Only windows the candidate explicitly stated. Empty if the answer is vague, declined or missing."
    )
