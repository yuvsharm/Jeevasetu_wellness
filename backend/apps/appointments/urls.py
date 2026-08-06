from django.urls import path

from apps.appointments.views import (
    AppointmentAssignmentView,
    AppointmentCreateView,
    AppointmentPhysiotherapistPhotoView,
    AppointmentStatusView,
    AvailablePhysiotherapistView,
    ConvertAppointmentRequestView,
    CustomerAppointmentCancelView,
    CustomerAppointmentDetailView,
    CustomerAppointmentListView,
    CustomerOperationalAppointmentListView,
    MyAssignedAppointmentListView,
    OperationalAppointmentDetailView,
    OperationalAppointmentListCreateView,
    OwnerAppointmentDetailView,
    OwnerAppointmentListView,
    TherapyListView,
)

urlpatterns = [
    path("schedule/", OperationalAppointmentListCreateView.as_view(), name="schedule-list"),
    path("schedule/<uuid:pk>/", OperationalAppointmentDetailView.as_view(), name="schedule-detail"),
    path("schedule/<uuid:pk>/assign/", AppointmentAssignmentView.as_view(), name="schedule-assign"),
    path("schedule/<uuid:pk>/status/", AppointmentStatusView.as_view(), name="schedule-status"),
    path(
        "schedule/<uuid:pk>/physiotherapist-photo/",
        AppointmentPhysiotherapistPhotoView.as_view(),
        name="schedule-physiotherapist-photo",
    ),
    path(
        "schedule/from-request/<uuid:request_id>/",
        ConvertAppointmentRequestView.as_view(),
        name="schedule-convert",
    ),
    path(
        "schedule/available-physiotherapists/",
        AvailablePhysiotherapistView.as_view(),
        name="schedule-available",
    ),
    path(
        "schedule/assigned-to-me/",
        MyAssignedAppointmentListView.as_view(),
        name="schedule-assigned-me",
    ),
    path(
        "schedule/my-appointments/",
        CustomerOperationalAppointmentListView.as_view(),
        name="schedule-customer-me",
    ),
    path("therapies/", TherapyListView.as_view(), name="appointment-therapy-list"),
    path("requests/", AppointmentCreateView.as_view(), name="appointment-create"),
    path("mine/", CustomerAppointmentListView.as_view(), name="appointment-mine"),
    path(
        "mine/<uuid:pk>/", CustomerAppointmentDetailView.as_view(), name="appointment-mine-detail"
    ),
    path(
        "mine/<uuid:pk>/cancel/", CustomerAppointmentCancelView.as_view(), name="appointment-cancel"
    ),
    path("owner/", OwnerAppointmentListView.as_view(), name="appointment-owner-list"),
    path("owner/<uuid:pk>/", OwnerAppointmentDetailView.as_view(), name="appointment-owner-detail"),
]
