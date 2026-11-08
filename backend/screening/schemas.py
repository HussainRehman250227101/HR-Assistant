"""Pydantic schema for structured transcript analysis (Azure GPT-5 mini)."""

from typing import Literal

from pydantic import BaseModel, Field


class QuestionAnswer(BaseModel):
    question_number: int = Field(description="1-based number of the approved question.")
    answer_status: Literal["ANSWERED", "UNCLEAR", "NOT_ASKED", "DECLINED_TO_ANSWER"]
    candidate_statement: str = Field(description="Exact words copied from a CANDIDATE line; empty if none.")
    agent_interpretation: str = Field(description="Short neutral interpretation, clearly separate from the statement.")


class RoleRequirementResponse(BaseModel):
    requirement: str
    candidate_statement: str = Field(description="Exact words copied from a CANDIDATE line; empty if none.")
    status: Literal["CONFIRMED", "PARTIAL", "NOT_CONFIRMED", "UNCLEAR"]


AnswerStatus = Literal["STATED", "DECLINED_TO_ANSWER", "NOT_ASKED", "UNCLEAR"]


class SalaryExpectation(BaseModel):
    """Standard question asked in every screening. Numbers are kept only if the quote is verified."""

    status: AnswerStatus
    minimum: float | None = Field(description="Lowest expected salary as a plain number (150k -> 150000); null if not stated.")
    maximum: float | None = Field(description="Highest expected salary; equal to minimum if one figure was given; null if not stated.")
    currency: str = Field(description="ISO 4217 code only if stated or unambiguous ('rupees' -> PKR, 'dollars' -> USD); else empty.")
    period: Literal["MONTHLY", "ANNUAL", "UNSPECIFIED"]
    candidate_statement: str = Field(description="Exact words copied from a CANDIDATE line; empty if none.")


class StatedAnswer(BaseModel):
    status: AnswerStatus
    summary: str = Field(description="Short neutral summary of what the candidate said; empty if not stated.")
    candidate_statement: str = Field(description="Exact words copied from a CANDIDATE line; empty if none.")


class ScreeningAnalysisOutput(BaseModel):
    call_outcome: Literal[
        "COMPLETED", "CONSENT_DECLINED", "HUMAN_REQUESTED", "STOPPED_BY_CANDIDATE",
        "VOICEMAIL", "POOR_AUDIO", "RESCHEDULE_REQUESTED", "INCOMPLETE",
    ]
    consent_status: Literal["GRANTED", "DECLINED", "NOT_ASKED", "UNCLEAR"]
    ai_disclosure_given: bool
    question_answers: list[QuestionAnswer]
    salary_expectation: SalaryExpectation
    notice_period: StatedAnswer = Field(description="Notice period or earliest start date.")
    interview_availability: StatedAnswer = Field(description="Days/times (and time zone) the candidate can interview.")
    role_requirement_responses: list[RoleRequirementResponse]
    candidate_questions: list[str]
    unresolved_questions: list[str]
    concise_summary: str
    recommended_next_step_for_human_review: Literal[
        "REVIEW_FOR_INTERVIEW_DECISION", "HUMAN_FOLLOW_UP_REQUIRED",
        "OFFER_ALTERNATIVE_SCREENING", "RETRY_CALL",
    ]
    warnings: list[str]
