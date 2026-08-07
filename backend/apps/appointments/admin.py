from django.contrib import admin

from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentChangeRequest,
    AppointmentRequest,
    ClinicOperatingHours,
    TherapyOption,
)

admin.site.register(
    (
        Appointment,
        AppointmentAuditEvent,
        AppointmentChangeRequest,
        AppointmentRequest,
        ClinicOperatingHours,
        TherapyOption,
    )
)
