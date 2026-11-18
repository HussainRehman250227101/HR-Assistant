"""Root URL configuration."""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path

from config.spa import spa_index

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
    path("api/v1/dashboard/", include("dashboard.urls")),
    path("api/v1/audit/", include("audit.urls")),
]

# Single-service deployment: everything that is not the API, admin or static files is a React route.
if settings.FRONTEND_DIST_DIR:
    urlpatterns.append(re_path(r"^(?!api/|admin/|static/).*$", spa_index))
