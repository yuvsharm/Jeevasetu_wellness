from django.db import migrations


def sync_current_therapy_memberships(apps, schema_editor):
    PractitionerCompetency = apps.get_model("practitioners", "PractitionerCompetency")
    active = PractitionerCompetency.objects.exclude(verification_status="REJECTED")
    for competency in active.filter(profile__staff_profile__isnull=False).select_related("profile"):
        competency.profile.staff_profile.therapy_competencies.add(competency.therapy_id)
    for competency in active.filter(
        application__approved_profile__staff_profile__isnull=False
    ).select_related("application__approved_profile"):
        competency.application.approved_profile.staff_profile.therapy_competencies.add(
            competency.therapy_id
        )


class Migration(migrations.Migration):
    dependencies = [("practitioners", "0008_practitionercompetency_created_at")]

    operations = [
        migrations.RunPython(sync_current_therapy_memberships, migrations.RunPython.noop),
    ]
