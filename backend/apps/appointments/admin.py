from django.contrib import admin

from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentRequest,
    ClinicOperatingHours,
    TherapyOption,
)

admin.site.register(
    (Appointment, AppointmentAuditEvent, AppointmentRequest, ClinicOperatingHours, TherapyOption)
)
