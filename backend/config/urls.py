"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/requisitions/", include("requisitions.urls")),
    path("api/v1/candidates/", include("candidates.urls")),
    path("api/v1/ai/", include("llm.urls")),
    path("api/v1/scoring/", include("scoring.urls")),
    path("api/v1/reviews/", include("reviews.urls")),
    path("api/v1/workflows/", include("workflows.urls")),
    path("api/v1/screening/", include("screening.urls")),
    path("api/v1/scheduling/", include("scheduling.urls")),
    path("api/v1/communications/", include("communications.urls")),
]
