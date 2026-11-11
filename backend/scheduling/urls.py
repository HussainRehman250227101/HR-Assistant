from django.urls import path

from .views import (
    AvailabilityDetailView, CalendarFeedView, CalendarSubscriptionView, AvailabilityListView, CandidateAutoScheduleView, CandidateInterviewView, InterviewCancelView,
    InterviewConfirmSlotView, InterviewDetailView, InterviewCompleteView, InterviewListView, InterviewReassignView, InterviewReproposeView,
)

app_name = "scheduling"
urlpatterns = [
    path("calendar/subscription/", CalendarSubscriptionView.as_view(), name="calendar-subscription"),
    path("calendar/<str:token>/interviews.ics", CalendarFeedView.as_view(), name="calendar-feed"),
    path("availability/", AvailabilityListView.as_view(), name="availability"),
    path("availability/<uuid:public_id>/", AvailabilityDetailView.as_view(), name="availability-detail"),
    path("interviews/", InterviewListView.as_view(), name="interviews"),
    path("candidates/<uuid:candidate_id>/interviews/", CandidateInterviewView.as_view(), name="candidate-interviews"),
    path("candidates/<uuid:candidate_id>/interviews/auto/", CandidateAutoScheduleView.as_view(), name="candidate-interview-auto"),
    path("interviews/<uuid:public_id>/", InterviewDetailView.as_view(), name="interview-detail"),
    path("interviews/<uuid:public_id>/propose/", InterviewReproposeView.as_view(), name="interview-propose"),
    path("interviews/<uuid:public_id>/confirm-slot/", InterviewConfirmSlotView.as_view(), name="interview-confirm-slot"),
    path("interviews/<uuid:public_id>/complete/", InterviewCompleteView.as_view(), name="interview-complete"),
    path("interviews/<uuid:public_id>/reassign/", InterviewReassignView.as_view(), name="interview-reassign"),
    path("interviews/<uuid:public_id>/cancel/", InterviewCancelView.as_view(), name="interview-cancel"),
]
