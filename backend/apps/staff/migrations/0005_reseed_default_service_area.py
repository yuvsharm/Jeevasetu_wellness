from django.db import migrations


def reseed_default_service_area(apps, schema_editor):
    Organization = apps.get_model("tenancy", "Organization")
    ServiceArea = apps.get_model("staff", "ServiceArea")
    for organization in Organization.objects.filter(is_active=True):
        if not ServiceArea.objects.filter(organization=organization, is_active=True).exists():
            ServiceArea.objects.create(
                organization=organization,
                name="Meerut",
                pin_codes=[],
                is_active=True,
            )


class Migration(migrations.Migration):
    dependencies = [("staff", "0004_optional_staff_dob_and_emergency_contact")]
    operations = [migrations.RunPython(reseed_default_service_area, migrations.RunPython.noop)]
