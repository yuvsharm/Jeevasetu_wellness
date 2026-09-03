from django.db import migrations, models
import django.core.validators


class Migration(migrations.Migration):
    dependencies = [("staff", "0003_staffprofile_therapy_competencies")]

    operations = [
        migrations.AlterField(
            model_name="staffprofile",
            name="date_of_birth",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="staffprofile",
            name="emergency_contact",
            field=models.CharField(
                blank=True,
                max_length=10,
                validators=[django.core.validators.RegexValidator("^[6-9]\\d{9}$")],
            ),
        ),
    ]
