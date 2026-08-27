from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("appointments", "0016_optional_authenticated_booking_details")]

    operations = [
        migrations.AddField(
            model_name="clinicoperatinghours",
            name="daily_schedule",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
