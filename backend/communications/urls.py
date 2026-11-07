from django.urls import path

from .views import ApproveSendView, CommunicationDetailView, CommunicationListView, DiscardView, InterviewDraftView

app_name = "communications"
urlpatterns = [
    path("", CommunicationListView.as_view(), name="list"),
    path("interviews/<uuid:interview_id>/draft/", InterviewDraftView.as_view(), name="interview-draft"),
    path("<uuid:public_id>/", CommunicationDetailView.as_view(), name="detail"),
    path("<uuid:public_id>/approve-send/", ApproveSendView.as_view(), name="approve-send"),
    path("<uuid:public_id>/discard/", DiscardView.as_view(), name="discard"),
]
