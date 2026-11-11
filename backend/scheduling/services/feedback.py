"""The assigned interviewer marks an interview done and rates every question the administrator set (Poor/Average/Good).

Decision support for HR only: the record never changes the candidate's pipeline status by itself.
"""

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from candidates.models import CandidateEvent
from accounts.permissions import has_full_access
from candidates.services.status import record_event
from ..models import FeedbackRating, Interview, InterviewFeedback, InterviewStatus
from .slots import SchedulingError

EVENT = CandidateEvent.EventType
COMPLETABLE = (InterviewStatus.SCHEDULED, InterviewStatus.SLOT_CONFIRMED)


def complete_interview(interview, actor, answers, comment=""):
    testing = settings.INTERVIEW_TESTING_MODE  # testing only: HR/admin may also mark it done, at any time
    if interview.interviewer_id != actor.pk and not (testing and has_full_access(actor)):
        raise SchedulingError("Only the interviewer assigned to this interview can mark it done.")
    if interview.status == InterviewStatus.COMPLETED:
        raise SchedulingError("This interview is already marked done.")
    if interview.status not in COMPLETABLE or not (interview.confirmed_start or testing):
        raise SchedulingError("Only a scheduled interview can be marked done.")
    if not testing and interview.confirmed_start > timezone.now():
        raise SchedulingError("The interview has not started yet. You can mark it done once it has taken place.")
    questions = list(interview.requisition.interview_questions or [])
    by_index = {}
    for item in answers or []:
        if item["index"] in by_index:
            raise SchedulingError("Each question can be answered only once.")
        by_index[item["index"]] = item["rating"]
    if set(by_index) != set(range(len(questions))):
        raise SchedulingError("Answer every interview question with Poor, Average or Good.")
    snapshot = [{"question": q, "rating": FeedbackRating(by_index[i]).value} for i, q in enumerate(questions)]
    try:
        with transaction.atomic():
            locked = Interview.objects.select_for_update().get(pk=interview.pk)
            if locked.status == InterviewStatus.COMPLETED:
                raise SchedulingError("This interview is already marked done.")
            feedback = InterviewFeedback.objects.create(
                interview=locked, submitted_by=actor, answers=snapshot, comment=(comment or "").strip())
            locked.status = InterviewStatus.COMPLETED
            locked.save(update_fields=("status", "updated_at"))
            record_event(locked.candidate, actor, EVENT.INTERVIEW_COMPLETED, interview_id=str(locked.public_id),
                         overall_rating=feedback.overall_rating, questions=len(snapshot))
    except IntegrityError as exc:
        raise SchedulingError("This interview is already marked done.") from exc
    interview.refresh_from_db()
    return interview
