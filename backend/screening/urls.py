from django.urls import path

from .views import (
    CandidateScreeningListView, ElevenLabsWebhookView, ScreeningAgentConfigView, ScreeningCancelView,
    ScreeningDetailView, ScreeningManualResultView, ScreeningPlaceCallView, ScreeningQueueView,
    ScreeningRetryAnalysisView, ScreeningReviewView, ScreeningSyncView,
)

app_name = "screening"
urlpatterns = [
    path("", ScreeningQueueView.as_view(), name="queue"),
    path("agent-config/", ScreeningAgentConfigView.as_view(), name="agent-config"),
    path("webhooks/elevenlabs/", ElevenLabsWebhookView.as_view(), name="elevenlabs-webhook"),
    path("candidates/<uuid:candidate_id>/", CandidateScreeningListView.as_view(), name="candidate-screenings"),
    path("<uuid:public_id>/", ScreeningDetailView.as_view(), name="detail"),
    path("<uuid:public_id>/call/", ScreeningPlaceCallView.as_view(), name="place-call"),
    path("<uuid:public_id>/sync/", ScreeningSyncView.as_view(), name="sync"),
    path("<uuid:public_id>/retry-analysis/", ScreeningRetryAnalysisView.as_view(), name="retry-analysis"),
    path("<uuid:public_id>/manual-result/", ScreeningManualResultView.as_view(), name="manual-result"),
    path("<uuid:public_id>/cancel/", ScreeningCancelView.as_view(), name="cancel"),
    path("<uuid:public_id>/review/", ScreeningReviewView.as_view(), name="review"),
]
