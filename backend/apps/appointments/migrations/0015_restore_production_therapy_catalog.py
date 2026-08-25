from django.db import migrations


# Restores the catalog already defined by the original seed and approved public
# content. Values are intentionally data-only: the commercial models remain the
# authority after migration and can still be managed by operations.
THERAPIES = (
    ("abhyang", "Abhyang", 500, 60, "A rhythmic full-body oil massage designed to support relaxation and everyday wellbeing.", ["Deep relaxation", "Supports mobility", "Nourishes the skin"]),
    ("potli-massage", "Potli Massage", 600, 60, "Warm herbal poultices are applied with skilled massage techniques for a comforting experience.", ["Soothing warmth", "Relaxed muscles", "Restorative care"]),
    ("shirodhara", "Shirodhara", 1800, 45, "A continuous stream of warm oil is gently directed over the forehead in a calm home setting.", ["Promotes calm", "Encourages rest", "Mindful relaxation"]),
    ("basti", "Basti", 500, 40, "A traditional localized oil-retention therapy delivered after an individual consultation.", ["Focused care", "Warm oil support", "Personalized session"]),
    ("jannu-basti", "Jannu Basti", 2000, 50, "A localized warm-oil therapy focused around the knee area for thoughtful, targeted care.", ["Knee-focused care", "Comforting warmth", "Supports flexibility"]),
    ("kati-basti", "Kati Basti", 1900, 50, "Warm medicated oil is retained over the lower back within a traditional dough boundary.", ["Lower-back focus", "Deep comfort", "Relaxing warmth"]),
    ("griva-basti", "Griva Basti", 1900, 50, "A carefully administered localized oil therapy focused on the neck and upper-back region.", ["Neck-focused care", "Comfort and ease", "Supports relaxation"]),
    ("akshiyarpah-both-eyes", "Akshiyarpah (Both Eyes)", 1500, 40, "A traditional eye-area wellness ritual performed with careful preparation and hygiene.", ["Restful ritual", "Gentle eye-area care", "Calming pause"]),
    ("nasya", "Nasya", 1000, 30, "A traditional Ayurvedic nasal-care ritual provided after suitability is discussed with you.", ["Traditional care", "Personal guidance", "Comfort-led session"]),
    ("deeptishu-massage", "Deeptishu Massage", 800, 60, "A focused massage experience combining attentive technique with warm natural oils.", ["Personalized pressure", "Relaxing care", "At-home comfort"]),
)


def restore_catalog(apps, schema_editor):
    Organization = apps.get_model("tenancy", "Organization")
    TherapyOption = apps.get_model("appointments", "TherapyOption")
    organization = Organization.objects.filter(slug="jeevasetu-wellness").first()
    if not organization:
        return

    production_slugs = {item[0] for item in THERAPIES}
    TherapyOption.objects.filter(organization=organization, slug__startswith="runtime-").exclude(
        slug__in=production_slugs
    ).update(is_publicly_visible=False)

    for order, (slug, name, price, duration, description, benefits) in enumerate(THERAPIES, 1):
        TherapyOption.objects.update_or_create(
            organization=organization,
            slug=slug,
            defaults={
                "name": name,
                "is_active": True,
                "is_publicly_visible": True,
                "display_order": order,
                "default_duration_minutes": duration,
                "base_price": price,
                "short_description": description,
                "detailed_description": description,
                "benefits": benefits,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("appointments", "0014_alter_therapyoption_options_and_more")]
    operations = [migrations.RunPython(restore_catalog, migrations.RunPython.noop)]
