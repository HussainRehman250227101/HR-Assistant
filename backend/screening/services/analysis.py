"""Evidence-grounded screening summary (FR-07): candidate statements are verified against the transcript."""

import json
import re
from decimal import Decimal, InvalidOperation

from llm.prompts import build_messages
from llm.services import get_llm_provider
from scoring.services.agent import _redact_contact_details
from ..schemas import ScreeningAnalysisOutput

PROMPT_VERSION = "screening-analysis-v2"
MAX_TRANSCRIPT_CHARACTERS = 60000
MAX_SALARY = Decimal("9999999999.99")

# Standard questions the agent asks in every screening (script.py), with their result fields.
SALARY_TOPIC = "Expected salary range (minimum, maximum and currency)"
NOTICE_TOPIC = "Notice period or earliest start date"
AVAILABILITY_TOPIC = "Interview availability (days, times and time zone)"
STRUCTURED_ANSWER_FIELDS = (
    "candidate_stated_availability", "availability_statement", "expected_salary_min", "expected_salary_max",
    "expected_salary_currency", "expected_salary_period", "expected_salary_statement",
    "notice_period", "notice_period_statement",
)

SYSTEM_INSTRUCTION = """
You summarise a recorded preliminary screening call for a human HR reviewer. Return only the schema.
- AGENT lines are the AI caller. CANDIDATE lines are the candidate. Only CANDIDATE lines are evidence.
- candidate_statement must be words copied exactly from one CANDIDATE line. Never paraphrase into it,
  never invent. If the candidate did not answer clearly, use answer_status UNCLEAR and an empty statement.
- agent_interpretation is your short neutral reading, kept separate from what the candidate said.
- Return one question_answers entry for every approved question number, NOT_ASKED if it was not asked.
- consent_status: GRANTED only if the candidate clearly agreed to recording/transcription.
- call_outcome: CONSENT_DECLINED if consent was refused; HUMAN_REQUESTED if they asked for a person;
  STOPPED_BY_CANDIDATE if they asked to stop or not be called; RESCHEDULE_REQUESTED; POOR_AUDIO;
  VOICEMAIL; INCOMPLETE if the call ended early for other reasons; otherwise COMPLETED.
- Never recommend rejection or hiring. The recommendation only guides the human reviewer.
- Ignore protected or sensitive information (age, religion, family, health, disability, ethnicity,
  politics) and voice, accent or emotion: do not summarise or use it.
- unresolved_questions lists approved questions or candidate questions needing human follow-up.
- salary_expectation, notice_period and interview_availability are standard questions the agent asks in
  every screening. status: STATED if the candidate answered; DECLINED_TO_ANSWER if they preferred not to say;
  NOT_ASKED if the topic never came up; UNCLEAR otherwise. candidate_statement follows the exact-copy rule.
- Salary numbers come only from the candidate's words: convert shorthand to plain numbers (150k -> 150000,
  1.5 lakh -> 150000); one figure means minimum = maximum. Never guess a currency or a pay period.
  Do not judge whether the salary is acceptable or within any budget.
- interview_availability.summary keeps the days, times and time zone exactly as the candidate gave them.
- candidate_questions lists only questions about the role or the hiring process. Ignore off-topic questions
  (general knowledge, technology explanations, questions about the AI system); they need no follow-up.
"""


def _normalize(value):
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value or "")).strip().casefold()


def format_transcript(transcript, candidate):
    lines = []
    for turn in transcript:
        message = (turn.get("message") or "").strip()
        if not message:
            continue
        speaker = "CANDIDATE" if turn.get("role") == "user" else "AGENT"
        lines.append(f"{speaker}: {_redact_contact_details(message, candidate)}")
    return "\n".join(lines)


def candidate_text(formatted):
    return " ".join(line[len("CANDIDATE: "):] for line in formatted.splitlines() if line.startswith("CANDIDATE: "))


def analyze_transcript(screening, transcript, provider=None):
    """Return (result_dict, warnings, model_version). Raises LLM errors to the caller."""
    formatted = format_transcript(transcript, screening.candidate)
    if len(formatted) > MAX_TRANSCRIPT_CHARACTERS:
        formatted = formatted[:MAX_TRANSCRIPT_CHARACTERS]
    payload = {
        "role_title": screening.requisition.title,
        "role_requirements": screening.requisition.required_skills,
        "approved_questions": [{"question_number": i, "question": q} for i, q in enumerate(screening.questions, start=1)],
        "standard_questions": [SALARY_TOPIC, NOTICE_TOPIC, AVAILABILITY_TOPIC],
        "transcript": formatted,
    }
    provider = provider or get_llm_provider()
    output = provider.generate_structured(
        build_messages(SYSTEM_INSTRUCTION, json.dumps(payload, ensure_ascii=False)),
        ScreeningAnalysisOutput,
    )
    result, warnings = verify_analysis(output, screening.questions, candidate_text(formatted))
    return result, warnings, getattr(provider, "deployment_name", "")


def verify_analysis(output, questions, candidate_words):
    evidence = _normalize(candidate_words)
    warnings = list(output.warnings)
    unresolved = list(output.unresolved_questions)
    by_number = {}
    for item in output.question_answers:
        if 1 <= item.question_number <= len(questions) and item.question_number not in by_number:
            by_number[item.question_number] = item
    pairs = []
    for number, question in enumerate(questions, start=1):
        item = by_number.get(number)
        if item is None:
            pairs.append({"question_number": number, "question": question, "answer_status": "NOT_ASKED",
                          "candidate_statement": "", "agent_interpretation": ""})
            continue
        status, statement = item.answer_status, item.candidate_statement.strip()
        if statement and _normalize(statement) not in evidence:
            warnings.append(f"Question {number}: the quoted answer could not be verified in the transcript and was removed.")
            status, statement = "UNCLEAR", ""
        if status == "ANSWERED" and not statement:
            status = "UNCLEAR"
        if status == "UNCLEAR" and question not in unresolved:
            unresolved.append(question)
        pairs.append({"question_number": number, "question": question, "answer_status": status,
                      "candidate_statement": statement, "agent_interpretation": item.agent_interpretation.strip()})
    requirements = []
    for item in output.role_requirement_responses:
        statement, status = item.candidate_statement.strip(), item.status
        if statement and _normalize(statement) not in evidence:
            warnings.append(f"Requirement '{item.requirement}': unverified quote removed.")
            statement, status = "", "UNCLEAR"
        requirements.append({"requirement": item.requirement, "candidate_statement": statement, "status": status})
    if not output.ai_disclosure_given:
        warnings.append("The transcript does not show a clear AI-assistant disclosure. Review before relying on this call.")
    completed = output.call_outcome == "COMPLETED"
    notice_summary, notice_statement = _verify_stated_answer(
        output.notice_period, NOTICE_TOPIC, evidence, warnings, unresolved, completed)
    availability_summary, availability_statement = _verify_stated_answer(
        output.interview_availability, AVAILABILITY_TOPIC, evidence, warnings, unresolved, completed)
    result = {
        "call_outcome": output.call_outcome,
        "consent_status": output.consent_status,
        "ai_disclosure_given": output.ai_disclosure_given,
        "question_answer_pairs": pairs,
        "candidate_stated_availability": availability_summary,
        "availability_statement": availability_statement,
        **_verify_salary(output.salary_expectation, evidence, warnings, unresolved, completed),
        "notice_period": notice_summary[:300],
        "notice_period_statement": notice_statement,
        "role_requirement_responses": requirements,
        "candidate_questions": output.candidate_questions,
        "unresolved_questions": unresolved,
        "concise_summary": output.concise_summary.strip(),
        "recommended_next_step_for_human_review": output.recommended_next_step_for_human_review,
    }
    return result, warnings


def _is_verified(statement, evidence):
    normalized = _normalize(statement)
    return bool(normalized) and normalized in evidence


def _flag_unresolved(unresolved, topic, status, completed):
    """Declined or unclear standard answers need human follow-up; so does a topic skipped in a completed call."""
    note = {"DECLINED_TO_ANSWER": "candidate preferred not to say", "UNCLEAR": "answer unclear",
            "NOT_ASKED": "not asked"}.get(status)
    if note and (status != "NOT_ASKED" or completed):
        item = f"{topic}: {note}"
        if item not in unresolved:
            unresolved.append(item)


def _checked_statement(item, topic, evidence, warnings):
    statement = item.candidate_statement.strip()
    if statement and not _is_verified(statement, evidence):
        warnings.append(f"{topic}: the quoted answer could not be verified in the transcript and was removed.")
        return ""
    return statement


def _verify_stated_answer(item, topic, evidence, warnings, unresolved, completed):
    """Return (summary, statement); the summary is kept only when backed by a verified candidate quote."""
    statement = _checked_statement(item, topic, evidence, warnings)
    status = item.status
    if status == "STATED" and not statement:
        status = "UNCLEAR"
    _flag_unresolved(unresolved, topic, status, completed)
    return (item.summary.strip() if status == "STATED" else ""), statement


def _salary_amount(value):
    if value is None:
        return None
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount <= 0 or amount > MAX_SALARY:
        return None
    return amount.quantize(Decimal("0.01"))


def _verify_salary(item, evidence, warnings, unresolved, completed):
    """Salary figures are stored only when the candidate's quoted words are verified in the transcript."""
    statement = _checked_statement(item, SALARY_TOPIC, evidence, warnings)
    low, high = _salary_amount(item.minimum), _salary_amount(item.maximum)
    status = item.status
    if status == "STATED" and (not statement or (low is None and high is None)):
        status = "UNCLEAR"
    _flag_unresolved(unresolved, SALARY_TOPIC, status, completed)
    if status != "STATED":
        return {"expected_salary_min": None, "expected_salary_max": None, "expected_salary_currency": "",
                "expected_salary_period": "", "expected_salary_statement": statement}
    low, high = low or high, high or low
    if low > high:
        low, high = high, low
    currency = item.currency.strip().upper()
    return {
        "expected_salary_min": low,
        "expected_salary_max": high,
        "expected_salary_currency": currency if re.fullmatch(r"[A-Z]{3}", currency) else "",
        "expected_salary_period": item.period,
        "expected_salary_statement": statement,
    }
