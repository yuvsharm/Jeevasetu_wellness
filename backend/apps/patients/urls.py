from django.urls import path

from apps.patients.views import (
    MyPatientProfileView,
    PatientDetailView,
    PatientListCreateView,
    PatientPhotoView,
    PatientStatusView,
    CustomerFamilyMemberListCreateView,
)

urlpatterns = [
    path("", PatientListCreateView.as_view(), name="patient-list-create"),
    path("me/", MyPatientProfileView.as_view(), name="patient-me"),
    path("family/", CustomerFamilyMemberListCreateView.as_view(), name="customer-family"),
    path("<uuid:pk>/", PatientDetailView.as_view(), name="patient-detail"),
    path("<uuid:pk>/status/", PatientStatusView.as_view(), name="patient-status"),
    path("<uuid:pk>/photo/", PatientPhotoView.as_view(), name="patient-photo"),
]
