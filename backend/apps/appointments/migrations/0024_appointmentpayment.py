import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0023_appointment_service_latitude_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AppointmentPayment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("amount_due", models.DecimalField(decimal_places=2, max_digits=10)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("PAID", "Paid")], default="PENDING", max_length=12)),
                ("paid_at", models.DateTimeField(blank=True, null=True)),
                ("reference", models.CharField(blank=True, max_length=120)),
                ("note", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("appointment", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="payment", to="appointments.appointment")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="tenancy.organization")),
                ("updated_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="updated_appointment_payments", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at",)},
        ),
    ]
