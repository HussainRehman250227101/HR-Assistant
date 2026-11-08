"""LangGraph execution, SQLite checkpointing, and human-review resumption."""

import logging
import os
from pathlib import Path

os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"

from django.conf import settings
from django.utils import timezone
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from candidates.models import CandidateEvent
from .graph import build_candidate_scoring_graph
from .models import WorkflowRun, WorkflowRunStatus

logger = logging.getLogger(__name__)


def _graph_context():
    checkpoint_path = Path(settings.LANGGRAPH_CHECKPOINT_DB_PATH)
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteSaver.from_conn_string(str(checkpoint_path))


def _thread_config(run):
    return {"configurable": {"thread_id": str(run.thread_id)}}


def _mark_failed(run, code, message):
    run.status = WorkflowRunStatus.FAILED
    run.error_code = code
    run.error_message = message
    run.current_step = "FAILED"
    run.save(update_fields=("status", "error_code", "error_message", "current_step", "updated_at"))
    CandidateEvent.objects.create(
        candidate=run.candidate,
        actor=run.created_by,
        event_type=CandidateEvent.EventType.WORKFLOW_FAILED,
        details={"workflow_run_id": str(run.public_id), "error_code": code, "trigger": run.trigger},
    )


def start_scoring_workflow(run):
    """Score one candidate, persist the checkpoint and pause for authorized HR review."""
    run.status = WorkflowRunStatus.RUNNING
    run.current_step = "SCORE_RESUME"
    run.started_at = timezone.now()
    run.error_code = ""
    run.error_message = ""
    run.save(update_fields=("status", "current_step", "started_at", "error_code", "error_message", "updated_at"))
    try:
        initial_state = {
            "workflow_run_id": str(run.public_id),
            "candidate_pk": run.candidate_id,
            "candidate_public_id": str(run.candidate.public_id),
            "resume_document_public_id": str(run.resume_document.public_id),
            "actor_pk": run.created_by_id,
        }
        config = _thread_config(run)
        with _graph_context() as checkpointer:
            checkpointer.setup()
            graph = build_candidate_scoring_graph(checkpointer)
            result = graph.invoke(initial_state, config)
            # Read the checkpoint state as the canonical source of the persisted evaluation ID.
            state_values = graph.get_state(config).values
        if result.get("__interrupt__") or state_values.get("review_request"):
            evaluation_pk = state_values.get("evaluation_pk") or result.get("evaluation_pk")
            run.refresh_from_db()
            run.evaluation_id = evaluation_pk
            run.status = WorkflowRunStatus.WAITING_HR_REVIEW
            run.current_step = "WAITING_HR_REVIEW"
            run.state_summary = {
                "evaluation_public_id": state_values.get("evaluation_public_id"),
                "overall_score": state_values.get("overall_score"),
                "confidence_level": state_values.get("confidence_level"),
                "recommendation": state_values.get("recommendation"),
            }
            run.save(update_fields=("evaluation", "status", "current_step", "state_summary", "updated_at"))
            CandidateEvent.objects.create(
                candidate=run.candidate,
                actor=run.created_by,
                event_type=CandidateEvent.EventType.WORKFLOW_STARTED,
                details={
                    "workflow_run_id": str(run.public_id),
                    "evaluation_id": str(run.evaluation.public_id),
                    "status": run.status,
                    "trigger": run.trigger,
                },
            )
        else:
            _mark_failed(run, "WORKFLOW_INTERRUPT_MISSING", "The scoring workflow did not pause for required HR review.")
    except Exception as exc:
        logger.error(
            "Scoring workflow failed. workflow_run=%s exception_type=%s",
            run.public_id, type(exc).__name__,
        )
        _mark_failed(
            run,
            "SCORING_WORKFLOW_FAILED",
            "The scoring workflow failed. Review the evaluation and retry the workflow.",
        )
    run.refresh_from_db()
    return run


def resume_workflow_after_review(run, review):
    """Resume a paused graph using a persisted human decision record."""
    run.refresh_from_db()
    if run.status == WorkflowRunStatus.COMPLETED:
        return run
    if run.status not in {WorkflowRunStatus.WAITING_HR_REVIEW, WorkflowRunStatus.FAILED}:
        raise ValueError("This workflow is not waiting for a recruiter decision.")
    if not run.evaluation_id or review.evaluation_id != run.evaluation_id:
        raise ValueError("The shortlist decision does not match this workflow evaluation.")

    run.status = WorkflowRunStatus.RUNNING
    run.current_step = "RESUMING_AFTER_HR_REVIEW"
    run.error_code = ""
    run.error_message = ""
    run.save(update_fields=("status", "current_step", "error_code", "error_message", "updated_at"))
    resume_payload = {
        "review_id": str(review.public_id),
        "decision": review.decision,
        "resulting_candidate_status": review.resulting_candidate_status,
    }
    try:
        config = _thread_config(run)
        with _graph_context() as checkpointer:
            checkpointer.setup()
            graph = build_candidate_scoring_graph(checkpointer)
            result = graph.invoke(Command(resume=resume_payload), config)
        if result.get("workflow_result") != "COMPLETED":
            raise RuntimeError("LangGraph did not complete after the recruiter decision.")
        run.status = WorkflowRunStatus.COMPLETED
        run.current_step = "COMPLETED"
        run.completed_at = timezone.now()
        run.state_summary = {
            **(run.state_summary or {}),
            "review_public_id": str(review.public_id),
            "decision": review.decision,
        }
        run.save(update_fields=("status", "current_step", "completed_at", "state_summary", "updated_at"))
        CandidateEvent.objects.create(
            candidate=run.candidate,
            actor=review.decided_by,
            event_type=CandidateEvent.EventType.WORKFLOW_COMPLETED,
            details={"workflow_run_id": str(run.public_id), "review_id": str(review.public_id)},
        )
    except Exception as exc:
        logger.error(
            "Workflow review resumption failed. workflow_run=%s exception_type=%s",
            run.public_id, type(exc).__name__,
        )
        _mark_failed(
            run,
            "WORKFLOW_RESUME_FAILED",
            "The recruiter decision was saved, but the workflow did not resume. Retry workflow resumption.",
        )
        raise
    return run


def retry_workflow_resume(run):
    """Retry resumption using the latest already-persisted shortlist decision."""
    if not run.evaluation_id:
        raise ValueError("This workflow has no saved evaluation to resume.")
    review = run.evaluation.shortlist_reviews.order_by("-created_at").first()
    if not review:
        raise ValueError("No saved shortlist decision exists for this workflow.")
    return resume_workflow_after_review(run, review)
