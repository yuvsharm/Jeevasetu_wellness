from django.db import migrations

THERAPIES = (
    ("abhyang", "Abhyang"),
    ("potli-massage", "Potli Massage"),
    ("shirodhara", "Shirodhara"),
    ("basti", "Basti"),
    ("jannu-basti", "Jannu Basti"),
    ("kati-basti", "Kati Basti"),
    ("griva-basti", "Griva Basti"),
    ("akshiyarpah-both-eyes", "Akshiyarpah (Both Eyes)"),
    ("nasya", "Nasya"),
    ("deeptishu-massage", "Deeptishu Massage"),
)


def seed_therapies(apps, schema_editor):
    Organization = apps.get_model("tenancy", "Organization")
    TherapyOption = apps.get_model("appointments", "TherapyOption")
    organization = Organization.objects.filter(slug="jeevasetu-wellness").first()
    if organization:
        for slug, name in THERAPIES:
            TherapyOption.objects.update_or_create(
                organization=organization,
                slug=slug,
                defaults={"name": name, "is_active": True},
            )


class Migration(migrations.Migration):
    dependencies = [("appointments", "0001_initial")]
    operations = [migrations.RunPython(seed_therapies, migrations.RunPython.noop)]
