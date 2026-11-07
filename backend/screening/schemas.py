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


class ScreeningAnalysisOutput(BaseModel):
    call_outcome: Literal[
        "COMPLETED", "CONSENT_DECLINED", "HUMAN_REQUESTED", "STOPPED_BY_CANDIDATE",
        "VOICEMAIL", "POOR_AUDIO", "RESCHEDULE_REQUESTED", "INCOMPLETE",
    ]
    consent_status: Literal["GRANTED", "DECLINED", "NOT_ASKED", "UNCLEAR"]
    ai_disclosure_given: bool
    question_answers: list[QuestionAnswer]
    candidate_stated_availability: str
    role_requirement_responses: list[RoleRequirementResponse]
    candidate_questions: list[str]
    unresolved_questions: list[str]
    concise_summary: str
    recommended_next_step_for_human_review: Literal[
        "REVIEW_FOR_INTERVIEW_DECISION", "HUMAN_FOLLOW_UP_REQUIRED",
        "OFFER_ALTERNATIVE_SCREENING", "RETRY_CALL",
    ]
    warnings: list[str]
