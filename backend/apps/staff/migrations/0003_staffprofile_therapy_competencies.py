from django.db import migrations, models


def copy_approved_competencies(apps, schema_editor):
    StaffProfile = apps.get_model("staff", "StaffProfile")
    PractitionerCompetency = apps.get_model("practitioners", "PractitionerCompetency")
    through = StaffProfile.therapy_competencies.through
    for competency in PractitionerCompetency.objects.filter(
        verification_status="VERIFIED",
        application__approved_profile__staff_profile__isnull=False,
    ).values("application__approved_profile__staff_profile_id", "therapy_id"):
        through.objects.get_or_create(
            staffprofile_id=competency["application__approved_profile__staff_profile_id"],
            therapyoption_id=competency["therapy_id"],
        )


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0021_offer_only_free_therapy_addons"),
        ("practitioners", "0003_resubmitted_and_unique_documents"),
        ("staff", "0002_seed_staff_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="therapy_competencies",
            field=models.ManyToManyField(
                blank=True,
                related_name="competent_staff_profiles",
                to="appointments.therapyoption",
            ),
        ),
        migrations.RunPython(copy_approved_competencies, migrations.RunPython.noop),
    ]
