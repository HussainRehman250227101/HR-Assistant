from django.urls import path

from .views import (
    AutoScoringStatusView,
    CandidateScoringWorkflowStartView,
    WorkflowRunDetailView,
    WorkflowRunResumeView,
)

app_name = "workflows"
urlpatterns = [
    path("auto-scoring/", AutoScoringStatusView.as_view(), name="auto-scoring-status"),
    path("candidates/<uuid:candidate_id>/start-scoring/", CandidateScoringWorkflowStartView.as_view(), name="candidate-start-scoring"),
    path("<uuid:public_id>/", WorkflowRunDetailView.as_view(), name="workflow-run-detail"),
    path("<uuid:public_id>/resume/", WorkflowRunResumeView.as_view(), name="workflow-run-resume"),
]
