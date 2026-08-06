from django.db import migrations

SPECIALIZATIONS = (
    "General Physiotherapy",
    "Sports Physiotherapy",
    "Orthopaedic",
    "Neurological",
    "Geriatric",
    "Pediatric",
    "Women's Health",
    "Ayurveda Therapy",
    "Deep Tissue",
    "Manual Therapy",
)


def seed_options(apps, schema_editor):
    Organization = apps.get_model("tenancy", "Organization")
    ServiceArea = apps.get_model("staff", "ServiceArea")
    Specialization = apps.get_model("staff", "Specialization")
    for name in SPECIALIZATIONS:
        Specialization.objects.get_or_create(name=name)
    organization = Organization.objects.filter(slug="jeevasetu-wellness").first()
    if organization:
        ServiceArea.objects.get_or_create(
            organization=organization,
            name="Meerut",
            defaults={"pin_codes": []},
        )


class Migration(migrations.Migration):
    dependencies = [("staff", "0001_initial")]
    operations = [migrations.RunPython(seed_options, migrations.RunPython.noop)]
