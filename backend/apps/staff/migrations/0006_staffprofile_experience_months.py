import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("staff", "0005_reseed_default_service_area")]
    operations = [
        migrations.AddField(
            model_name="staffprofile",
            name="experience_months",
            field=models.PositiveSmallIntegerField(default=0, validators=[django.core.validators.MaxValueValidator(11)]),
        ),
    ]
