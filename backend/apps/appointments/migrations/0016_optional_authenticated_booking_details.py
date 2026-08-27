from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0015_restore_production_therapy_catalog"),
    ]

    operations = [
        migrations.AlterField(
            model_name="appointmentrequest",
            name="landmark",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AlterField(
            model_name="appointmentrequest",
            name="pain_area",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AlterField(
            model_name="appointmentrequest",
            name="problem_description",
            field=models.TextField(blank=True, default="", max_length=2000),
        ),
        migrations.AlterField(
            model_name="appointmentrequest",
            name="problem_duration",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
