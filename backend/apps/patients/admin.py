from django.contrib import admin

from apps.patients.models import CaregiverRelationship, PatientAddress, PatientProfile

admin.site.register((PatientProfile, PatientAddress, CaregiverRelationship))
