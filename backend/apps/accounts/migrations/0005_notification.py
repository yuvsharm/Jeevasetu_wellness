import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0004_roleassignment_acct_role_owner_org_scope_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("tenancy", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Notification",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("recipient_role", models.CharField(choices=[("OWNER", "Owner"), ("MANAGER", "Manager"), ("PHYSIOTHERAPIST", "Physiotherapist"), ("CUSTOMER", "Customer")], max_length=32)),
                ("notification_type", models.CharField(max_length=64)),
                ("category", models.CharField(choices=[("APPOINTMENTS", "Appointments"), ("PRACTITIONERS", "Practitioners"), ("PAYMENTS", "Payments"), ("REVIEWS", "Reviews")], max_length=24)),
                ("title", models.CharField(max_length=160)),
                ("message", models.CharField(blank=True, max_length=500)),
                ("related_object_type", models.CharField(max_length=64)),
                ("related_object_id", models.CharField(max_length=64)),
                ("target_url", models.CharField(max_length=500)),
                ("action_required", models.BooleanField(default=False)),
                ("dedupe_key", models.CharField(max_length=255)),
                ("read_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notifications", to="tenancy.organization")),
                ("recipient", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="notifications", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ("-created_at",),
                "indexes": [
                    models.Index(fields=["organization", "recipient", "recipient_role", "read_at", "created_at"], name="acct_notif_inbox_idx"),
                    models.Index(fields=["organization", "recipient", "recipient_role", "category", "read_at"], name="acct_notif_category_idx"),
                ],
                "constraints": [models.UniqueConstraint(fields=("organization", "recipient", "recipient_role", "dedupe_key"), name="acct_notification_dedupe_uniq")],
            },
        ),
    ]
