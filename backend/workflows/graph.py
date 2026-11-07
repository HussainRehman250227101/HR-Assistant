"""LangGraph workflow with a checkpointed human shortlist-review interrupt."""

import os
from typing import Any, TypedDict

os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

from django.contrib.auth import get_user_model
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from scoring.services.agent import evaluate_candidate_resume


class RecruitmentWorkflowState(TypedDict, total=False):
    workflow_run_id: str
    candidate_pk: int
    candidate_public_id: str
    resume_document_public_id: str
    actor_pk: int | None
    evaluation_pk: int
    evaluation_public_id: str
    overall_score: int | None
    confidence_level: str
    recommendation: str
    review_request: dict[str, Any]
    review_response: dict[str, Any]
    review_id: str
    decision: str
    workflow_result: str


def build_candidate_scoring_graph(checkpointer, scorer=None):
    """Build scoring-to-review workflow; the graph cannot decide shortlist outcomes."""
    scoring_function = scorer or evaluate_candidate_resume

    def score_node(state: RecruitmentWorkflowState):
        actor = None
        if state.get("actor_pk"):
            actor = get_user_model().objects.filter(pk=state["actor_pk"]).first()
        evaluation = scoring_function(
            candidate_id=state["candidate_pk"],
            resume_document_id=state["resume_document_public_id"],
            actor=actor,
        )
        review_request = {
            "event": "SHORTLIST_REVIEW_REQUIRED",
            "workflow_run_id": state["workflow_run_id"],
            "candidate_id": state["candidate_public_id"],
            "evaluation_id": str(evaluation.public_id),
            "overall_score": evaluation.overall_score,
            "confidence_level": str(evaluation.confidence_level),
            "recommendation": str(evaluation.recommendation_for_human_review),
            "message": "Recruiter review is required. No candidate contact or progression occurs automatically.",
        }
        return {
            "evaluation_pk": evaluation.pk,
            "evaluation_public_id": str(evaluation.public_id),
            "overall_score": evaluation.overall_score,
            "confidence_level": str(evaluation.confidence_level),
            "recommendation": str(evaluation.recommendation_for_human_review),
            "review_request": review_request,
        }

    def human_review_gate(state: RecruitmentWorkflowState):
        # No external action is performed before the checkpointed approval pause.
        response = interrupt(state["review_request"])
        return {"review_response": response}

    def finalize_node(state: RecruitmentWorkflowState):
        response = state.get("review_response") or {}
        return {
            "workflow_result": "COMPLETED",
            "review_id": str(response.get("review_id", "")),
            "decision": str(response.get("decision", "")),
        }

    builder = StateGraph(RecruitmentWorkflowState)
    builder.add_node("score_resume", score_node)
    builder.add_node("wait_for_hr_review", human_review_gate)
    builder.add_node("finalize_review", finalize_node)
    builder.add_edge(START, "score_resume")
    builder.add_edge("score_resume", "wait_for_hr_review")
    builder.add_edge("wait_for_hr_review", "finalize_review")
    builder.add_edge("finalize_review", END)
    return builder.compile(checkpointer=checkpointer)
