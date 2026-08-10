from django.db import migrations, models


def remove_duplicate_documents(apps, schema_editor):
    Document = apps.get_model("practitioners", "PractitionerDocument")
    seen = set()
    for document in Document.objects.order_by("-created_at", "-id"):
        key = (document.application_id, document.kind)
        if key in seen:
            document.delete()
        else:
            seen.add(key)


class Migration(migrations.Migration):
    dependencies = [("practitioners", "0002_practitionerapplication_availability_notes_and_more")]

    operations = [
        migrations.AlterField(
            model_name="practitionerapplication",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED", "Submitted"),
                    ("UNDER_REVIEW", "Under review"),
                    ("CORRECTION_REQUIRED", "Correction required"),
                    ("RESUBMITTED", "Resubmitted"),
                    ("APPROVED", "Approved"),
                    ("REJECTED", "Rejected"),
                    ("WITHDRAWN", "Withdrawn"),
                ],
                default="DRAFT",
                max_length=24,
            ),
        ),
        migrations.RunPython(remove_duplicate_documents, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="practitionerdocument",
            constraint=models.UniqueConstraint(
                fields=("application", "kind"), name="pract_doc_application_kind_uniq"
            ),
        ),
    ]
