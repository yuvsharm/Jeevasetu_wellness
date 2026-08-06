from django.contrib import admin

from apps.staff.models import ServiceArea, Specialization, StaffDocument, StaffProfile

admin.site.register((ServiceArea, Specialization, StaffDocument, StaffProfile))
