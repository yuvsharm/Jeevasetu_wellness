from django.contrib import admin

from apps.availability.models import (
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)

admin.site.register((AvailabilityRule, AvailabilityException, AvailabilityAuditEvent))
