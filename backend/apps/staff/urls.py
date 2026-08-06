from django.urls import path

from apps.staff.views import (
    AvailabilityView,
    ManagerPasswordResetView,
    MyStaffProfileView,
    StaffDetailView,
    StaffListCreateView,
    StaffOptionsView,
    StaffStatusView,
)

urlpatterns = [
    path("profiles/", StaffListCreateView.as_view(), name="staff-list"),
    path("profiles/<uuid:pk>/", StaffDetailView.as_view(), name="staff-detail"),
    path("profiles/<uuid:pk>/status/", StaffStatusView.as_view(), name="staff-status"),
    path(
        "profiles/<uuid:pk>/password-reset/",
        ManagerPasswordResetView.as_view(),
        name="staff-password-reset",
    ),
    path("me/", MyStaffProfileView.as_view(), name="staff-me"),
    path("me/availability/", AvailabilityView.as_view(), name="staff-availability"),
    path("options/", StaffOptionsView.as_view(), name="staff-options"),
]
