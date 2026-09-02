from django.db import migrations, models
import django.core.validators


ADDONS = (
    ("leg-massage", "Leg Massage"),
    ("head-massage", "Head Massage"),
)


def create_offer_addons(apps, schema_editor):
    TherapyOption = apps.get_model("appointments", "TherapyOption")
    Organization = apps.get_model("tenancy", "Organization")
    for organization in Organization.objects.all().iterator():
        for order, (slug, name) in enumerate(ADDONS, start=900):
            TherapyOption.objects.update_or_create(
                organization=organization,
                slug=slug,
                defaults={
                    "name": name,
                    "is_active": True,
                    "base_price": 0,
                    "is_publicly_visible": False,
                    "is_offer_free_addon": True,
                    "default_duration_minutes": 15,
                    "display_order": order,
                    "short_description": "Promotional free add-on only.",
                },
            )


def remove_offer_addons(apps, schema_editor):
    TherapyOption = apps.get_model("appointments", "TherapyOption")
    TherapyOption.objects.filter(
        slug__in=[slug for slug, _ in ADDONS],
        is_offer_free_addon=True,
        free_addon_offers__isnull=True,
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("appointments", "0020_commercialoffer_guided_rules")]
    operations = [
        migrations.AddField(
            model_name="therapyoption",
            name="is_offer_free_addon",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="therapyoption",
            name="default_duration_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(15),
                    django.core.validators.MaxValueValidator(180),
                ],
            ),
        ),
        migrations.RunPython(create_offer_addons, remove_offer_addons),
    ]
