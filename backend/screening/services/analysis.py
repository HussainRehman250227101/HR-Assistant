"""Evidence-grounded screening summary (FR-07): candidate statements are verified against the transcript."""

import json
import re

from llm.prompts import build_messages
from llm.services import get_llm_provider
from scoring.services.agent import _redact_contact_details
from ..schemas import ScreeningAnalysisOutput

PROMPT_VERSION = "screening-analysis-v1"
MAX_TRANSCRIPT_CHARACTERS = 60000

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
    result = {
        "call_outcome": output.call_outcome,
        "consent_status": output.consent_status,
        "ai_disclosure_given": output.ai_disclosure_given,
        "question_answer_pairs": pairs,
        "candidate_stated_availability": output.candidate_stated_availability.strip(),
        "role_requirement_responses": requirements,
        "candidate_questions": output.candidate_questions,
        "unresolved_questions": unresolved,
        "concise_summary": output.concise_summary.strip(),
        "recommended_next_step_for_human_review": output.recommended_next_step_for_human_review,
    }
    return result, warnings
