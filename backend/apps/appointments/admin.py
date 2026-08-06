from django.contrib import admin

from apps.appointments.models import AppointmentRequest, TherapyOption

admin.site.register((AppointmentRequest, TherapyOption))
