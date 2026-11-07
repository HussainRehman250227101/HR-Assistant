from django.urls import path

from .views import ActivityLogView, DashboardSummaryView, EventTypesView, PipelineView

app_name = "dashboard"
urlpatterns = [
    path("summary/", DashboardSummaryView.as_view(), name="summary"),
    path("pipeline/", PipelineView.as_view(), name="pipeline"),
    path("activity/", ActivityLogView.as_view(), name="activity"),
    path("event-types/", EventTypesView.as_view(), name="event-types"),
]
