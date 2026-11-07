"""Human gate 2 (SRS §13): HR reviews the screening result and explicitly chooses the next stage."""

from django.db import transaction

from candidates.models import Candidate, CandidateEvent, CandidateStatus
from candidates.services.status import change_candidate_status, record_event
from ..models import CallOutcome, Screening, ScreeningChannel, ScreeningDecision, ScreeningReview, ScreeningStatus
from .calls import ScreeningError, automated_call_blocker, create_screening


def review_screening(screening, actor, decision, reason):
    reason = (reason or "").strip()
    if decision != ScreeningDecision.APPROVE_FOR_INTERVIEW and not reason:
        raise ScreeningError("A reason is required for this decision.")
    if decision == ScreeningDecision.APPROVE_FOR_INTERVIEW and screening.call_status != CallOutcome.COMPLETED and not reason:
        raise ScreeningError("The screening did not complete normally; explain why the candidate is approved for interview.")
    with transaction.atomic():
        locked = Screening.objects.select_for_update().get(pk=screening.pk)
        if locked.status != ScreeningStatus.AWAITING_HR_REVIEW:
            raise ScreeningError("This screening is not awaiting HR review.")
        candidate = Candidate.objects.select_for_update().get(pk=locked.candidate_id)
        if candidate.current_status != CandidateStatus.SCREENING_COMPLETED_HR_REVIEW:
            raise ScreeningError("The candidate is not awaiting a screening decision.")
        if decision == ScreeningDecision.RESCREEN_AI_CALL:
            blocker = automated_call_blocker(candidate)
            if blocker:
                raise ScreeningError(blocker)
        previous = candidate.current_status
        locked.status = ScreeningStatus.REVIEWED
        locked.save(update_fields=("status", "updated_at"))
        follow_up = None
        if decision == ScreeningDecision.APPROVE_FOR_INTERVIEW:
            change_candidate_status(candidate, CandidateStatus.APPROVED_FOR_INTERVIEW, actor, "Screening approved by HR",
                                    screening_id=str(locked.public_id))
        elif decision == ScreeningDecision.DECLINE:
            candidate.closed_reason = reason
            candidate.save(update_fields=("closed_reason", "updated_at"))
            change_candidate_status(candidate, CandidateStatus.CLOSED, actor, "Declined after screening review",
                                    screening_id=str(locked.public_id))
        else:
            # Re-screening goes back through the approved-for-screening gate, then creates a fresh screening.
            change_candidate_status(candidate, CandidateStatus.APPROVED_FOR_SCREENING, actor, "Re-screening requested by HR",
                                    screening_id=str(locked.public_id))
            channel = ScreeningChannel.AI_VOICE if decision == ScreeningDecision.RESCREEN_AI_CALL else ScreeningChannel.HUMAN_LED
            follow_up = create_screening(candidate, actor, channel)
            candidate.refresh_from_db()
        review = ScreeningReview.objects.create(
            screening=locked, candidate=candidate, decision=decision, decision_reason=reason,
            previous_candidate_status=previous, resulting_candidate_status=candidate.current_status,
            follow_up_screening=follow_up, decided_by=actor,
        )
        record_event(candidate, actor, CandidateEvent.EventType.SCREENING_DECISION_RECORDED,
                     screening_id=str(locked.public_id), screening_review_id=str(review.public_id),
                     decision=decision, **{"from": previous, "to": candidate.current_status})
    return review
