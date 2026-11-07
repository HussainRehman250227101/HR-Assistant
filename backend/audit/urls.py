from django.urls import path

from .views import AuditEventListView

app_name = "audit"
urlpatterns = [path("", AuditEventListView.as_view(), name="list")]
