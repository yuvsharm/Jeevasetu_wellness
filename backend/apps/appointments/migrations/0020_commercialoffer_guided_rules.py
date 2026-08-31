from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("appointments", "0019_appointmentrequest_rejection_category_and_more")]
    operations = [
        migrations.AddField(
            model_name="commercialoffer",
            name="rule_config",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="commercialoffer",
            name="minimum_family_members",
            field=models.PositiveSmallIntegerField(
                default=1, validators=[django.core.validators.MinValueValidator(1)]
            ),
        ),
        migrations.AlterField(
            model_name="commercialoffer",
            name="offer_type",
            field=models.CharField(
                choices=[
                    ("PERCENTAGE", "Percentage discount"),
                    ("FIXED_DISCOUNT", "Fixed discount"),
                    ("FIXED_BUNDLE", "Fixed-price bundle"),
                    ("FREE_THERAPY", "Free therapy / add-on"),
                    ("FAMILY", "Family discount"),
                    ("THERAPY_DISCOUNT", "Therapy discount"),
                    ("FAMILY_FREE", "Family free therapy"),
                ],
                max_length=24,
            ),
        ),
    ]
