from django.urls import path

from apps.staff.views import (
    AvailabilityView,
    ManagerPasswordResetView,
    MyStaffProfileView,
    StaffDetailView,
    StaffListCreateView,
    StaffOptionsView,
    StaffMobileAvailabilityView,
    StaffStatusView,
    StaffPhotoView,
)

from apps.staff.self_profile import SelfMobileView, SelfPhotoView, SelfOptionsView, SelfCompetenciesView, ManagedCompetenciesView, SelfCredentialsView, CredentialReviewView, CredentialFileView

urlpatterns = [
    path("me/change-mobile/", SelfMobileView.as_view()),
    path("me/photo/", SelfPhotoView.as_view()),
    path("me/options/", SelfOptionsView.as_view()),
    path("me/competencies/", SelfCompetenciesView.as_view()),
    path("me/credentials/", SelfCredentialsView.as_view()),
    path("credentials/", CredentialReviewView.as_view()),
    path("credentials/<uuid:pk>/", CredentialFileView.as_view()),
    path("credentials/<uuid:pk>/review/", CredentialReviewView.as_view()),
    path("profiles/<uuid:pk>/photo/", StaffPhotoView.as_view(), name="staff-photo"),
    path("profiles/", StaffListCreateView.as_view(), name="staff-list"),
    path("profiles/<uuid:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path("profiles/<uuid:pk>/competencies/", ManagedCompetenciesView.as_view(), name="staff-competencies"),
    path("profiles/<uuid:pk>/status/", StaffStatusView.as_view(), name="staff-status"),
    path(
        "profiles/<uuid:pk>/password-reset/",
        ManagerPasswordResetView.as_view(),
        name="staff-password-reset",
    ),
    path("me/", MyStaffProfileView.as_view(), name="staff-me"),
    path("me/availability/", AvailabilityView.as_view(), name="staff-availability"),
    path("options/", StaffOptionsView.as_view(), name="staff-options"),
    path("mobile-availability/", StaffMobileAvailabilityView.as_view(), name="staff-mobile-availability"),
]
