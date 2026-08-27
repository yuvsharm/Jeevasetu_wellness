from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("appointments", "0017_clinicoperatinghours_daily_schedule")]

    operations = [
        migrations.AddField(
            model_name="clinicoperatinghours",
            name="minimum_advance_notice_hours",
            field=models.PositiveSmallIntegerField(
                default=24,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(168),
                ],
            ),
        ),
    ]
