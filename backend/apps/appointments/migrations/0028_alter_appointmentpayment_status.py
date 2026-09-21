from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("appointments", "0027_alter_appointment_journey_status")]

    operations = [
        migrations.AlterField(
            model_name="appointmentpayment",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending"),
                    ("VERIFICATION_PENDING", "Verification pending"),
                    ("PAID", "Paid"),
                ],
                default="PENDING",
                max_length=24,
            ),
        ),
    ]
