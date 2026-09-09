from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("practitioners", "0006_practitioner_experience"),
    ]

    operations = [
        migrations.AlterField(
            model_name="practitionercompetency",
            name="application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="competencies",
                to="practitioners.practitionerapplication",
            ),
        ),
        migrations.AddField(
            model_name="practitionercompetency",
            name="profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="competency_requests",
                to="practitioners.practitionerprofile",
            ),
        ),
        migrations.AddConstraint(
            model_name="practitionercompetency",
            constraint=models.UniqueConstraint(
                fields=("profile", "therapy"), name="pract_profile_therapy_uniq"
            ),
        ),
        migrations.AddConstraint(
            model_name="practitionercompetency",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(application__isnull=False, profile__isnull=True)
                    | models.Q(application__isnull=True, profile__isnull=False)
                ),
                name="pract_competency_single_parent",
            ),
        ),
    ]
