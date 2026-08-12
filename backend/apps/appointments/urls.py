from django.urls import path

from apps.appointments.views import (
    AppointmentAssignmentResponseView,
    AppointmentAssignmentView,
    AppointmentJourneyView,
    AppointmentAuditListView,
    AppointmentCalendarView,
    AppointmentCancellationView,
    AppointmentCreateView,
    AppointmentOperationsQueueView,
    AppointmentPhysiotherapistPhotoView,
    AppointmentRescheduleView,
    AppointmentStatusView,
    AppointmentUnassignmentView,
    AvailablePhysiotherapistView,
    ConvertAppointmentRequestView,
    CustomerAppointmentCancelView,
    CustomerAppointmentChangeRequestView,
    CustomerAppointmentDetailView,
    CustomerAppointmentListView,
    CustomerAppointmentRatingView,
    CustomerOperationalAppointmentListView,
    CustomerVisitVerificationView,
    MyAssignedAppointmentListView,
    OperationalAppointmentDetailView,
    OperationalAppointmentListCreateView,
    OwnerAppointmentDetailView,
    OwnerAppointmentListView,
    PhysiotherapistVisitVerificationView,
    PractitionerPaymentListView,
    OperationsPaymentView,
    PhysiotherapistWorkloadView,
    TherapyListView,
)

urlpatterns = [
    path("schedule/", OperationalAppointmentListCreateView.as_view(), name="schedule-list"),
    path("schedule/calendar/", AppointmentCalendarView.as_view(), name="schedule-calendar"),
    path(
        "schedule/operations/",
        AppointmentOperationsQueueView.as_view(),
        name="schedule-operations",
    ),
    path("schedule/<uuid:pk>/", OperationalAppointmentDetailView.as_view(), name="schedule-detail"),
    path("schedule/<uuid:pk>/assign/", AppointmentAssignmentView.as_view(), name="schedule-assign"),
    path(
        "schedule/<uuid:pk>/unassign/",
        AppointmentUnassignmentView.as_view(),
        name="schedule-unassign",
    ),
    path(
        "schedule/<uuid:pk>/assignment-response/",
        AppointmentAssignmentResponseView.as_view(),
        name="schedule-assignment-response",
    ),
    path("schedule/<uuid:pk>/status/", AppointmentStatusView.as_view(), name="schedule-status"),
    path("schedule/<uuid:pk>/journey/", AppointmentJourneyView.as_view(), name="schedule-journey"),
    path(
        "schedule/<uuid:pk>/reschedule/",
        AppointmentRescheduleView.as_view(),
        name="schedule-reschedule",
    ),
    path(
        "schedule/<uuid:pk>/cancel/",
        AppointmentCancellationView.as_view(),
        name="schedule-cancel",
    ),
    path(
        "schedule/<uuid:pk>/audit/",
        AppointmentAuditListView.as_view(),
        name="schedule-audit",
    ),
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
        "schedule/physiotherapist-workload/",
        PhysiotherapistWorkloadView.as_view(),
        name="schedule-physiotherapist-workload",
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
    path(
        "schedule/my-appointments/<uuid:pk>/change-requests/",
        CustomerAppointmentChangeRequestView.as_view(),
        name="schedule-customer-change-requests",
    ),
    path(
        "schedule/my-appointments/<uuid:pk>/visit-verification/",
        CustomerVisitVerificationView.as_view(),
        name="schedule-customer-visit-verification",
    ),
    path(
        "schedule/assigned-to-me/<uuid:pk>/visit-verification/",
        PhysiotherapistVisitVerificationView.as_view(),
        name="schedule-physiotherapist-visit-verification",
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
    path("schedule/my-appointments/<uuid:pk>/rating/", CustomerAppointmentRatingView.as_view(), name="schedule-customer-rating"),
    path("schedule/assigned-to-me/payments/", PractitionerPaymentListView.as_view(), name="schedule-practitioner-payments"),
    path("schedule/<uuid:pk>/payment/", OperationsPaymentView.as_view(), name="schedule-operations-payment"),
]
