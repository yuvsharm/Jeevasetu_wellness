import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("practitioners", "0007_practitionercompetency_profile_requests")]

    operations = [
        migrations.AddField(
            model_name="practitionercompetency",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
