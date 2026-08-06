from django.urls import path

from apps.appointments.views import (
    AppointmentCreateView,
    CustomerAppointmentCancelView,
    CustomerAppointmentDetailView,
    CustomerAppointmentListView,
    OwnerAppointmentDetailView,
    OwnerAppointmentListView,
    TherapyListView,
)

urlpatterns = [
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
