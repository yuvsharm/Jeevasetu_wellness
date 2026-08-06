from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

from config.health import (
    CeleryReadinessView,
    DatabaseReadinessView,
    LivenessView,
    ReadinessView,
    RedisReadinessView,
)

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/access/", include("apps.accounts.access_urls")),
    path("api/v1/health/live/", LivenessView.as_view(), name="health-live"),
    path("api/v1/tenancy/", include("apps.tenancy.urls")),
    path("api/v1/appointments/", include("apps.appointments.urls")),
    path("api/v1/staff/", include("apps.staff.urls")),
    path("api/v1/patients/", include("apps.patients.urls")),
    path("api/v1/health/ready/", ReadinessView.as_view(), name="health-ready"),
    path(
        "api/v1/health/ready/database/",
        DatabaseReadinessView.as_view(),
        name="health-ready-database",
    ),
    path(
        "api/v1/health/ready/redis/",
        RedisReadinessView.as_view(),
        name="health-ready-redis",
    ),
    path(
        "api/v1/health/ready/celery/",
        CeleryReadinessView.as_view(),
        name="health-ready-celery",
    ),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="api-schema"),
    path(
        "api/v1/docs/",
        SpectacularSwaggerView.as_view(url_name="api-schema"),
        name="api-docs",
    ),
    path(
        "api/v1/redoc/",
        SpectacularRedocView.as_view(url_name="api-schema"),
        name="api-redoc",
    ),
]
