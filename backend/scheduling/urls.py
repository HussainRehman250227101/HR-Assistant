from django.urls import path

from .views import (
    AvailabilityDetailView, AvailabilityListView, CandidateAutoScheduleView, CandidateInterviewView, InterviewCancelView,
    InterviewConfirmSlotView, InterviewDetailView, InterviewListView, InterviewReproposeView,
)

app_name = "scheduling"
urlpatterns = [
    path("availability/", AvailabilityListView.as_view(), name="availability"),
    path("availability/<uuid:public_id>/", AvailabilityDetailView.as_view(), name="availability-detail"),
    path("interviews/", InterviewListView.as_view(), name="interviews"),
    path("candidates/<uuid:candidate_id>/interviews/", CandidateInterviewView.as_view(), name="candidate-interviews"),
    path("candidates/<uuid:candidate_id>/interviews/auto/", CandidateAutoScheduleView.as_view(), name="candidate-interview-auto"),
    path("interviews/<uuid:public_id>/", InterviewDetailView.as_view(), name="interview-detail"),
    path("interviews/<uuid:public_id>/propose/", InterviewReproposeView.as_view(), name="interview-propose"),
    path("interviews/<uuid:public_id>/confirm-slot/", InterviewConfirmSlotView.as_view(), name="interview-confirm-slot"),
    path("interviews/<uuid:public_id>/cancel/", InterviewCancelView.as_view(), name="interview-cancel"),
]
