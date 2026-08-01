from django.contrib import admin
from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from config.health import HealthView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthView.as_view(), name="health"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="api-schema"),
]
