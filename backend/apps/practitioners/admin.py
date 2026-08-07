from django.contrib import admin

from apps.practitioners.models import (
    PractitionerApplication,
    PractitionerAuditEvent,
    PractitionerCompetency,
    PractitionerDocument,
    PractitionerProfile,
)

admin.site.register(PractitionerApplication)
admin.site.register(PractitionerCompetency)
admin.site.register(PractitionerDocument)
admin.site.register(PractitionerProfile)
admin.site.register(PractitionerAuditEvent)
