import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0024_appointmentpayment"),
        ("patients", "0003_patientaddress_latitude_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="appointmentrequest",
            name="booking_source",
            field=models.CharField(
                choices=[
                    ("ONLINE", "Online"),
                    ("CALL", "Call"),
                    ("ADVERTISEMENT", "Advertisement"),
                    ("REFERRAL", "Referral"),
                    ("WALK_IN", "Walk-in"),
                    ("OTHER", "Other"),
                ],
                default="ONLINE",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="appointmentrequest",
            name="patient_profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="appointment_requests",
                to="patients.patientprofile",
            ),
        ),
    ]
