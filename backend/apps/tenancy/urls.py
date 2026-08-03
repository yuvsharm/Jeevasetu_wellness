from django.urls import path

from apps.tenancy.views import ClinicDetailView, ClinicListView, OrganizationContextView

urlpatterns = [
    path("context/", OrganizationContextView.as_view(), name="tenant-context"),
    path("clinics/", ClinicListView.as_view(), name="tenant-clinic-list"),
    path("clinics/<uuid:pk>/", ClinicDetailView.as_view(), name="tenant-clinic-detail"),
]
