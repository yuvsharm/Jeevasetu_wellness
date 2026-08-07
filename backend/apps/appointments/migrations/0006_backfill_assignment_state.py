from django.db import migrations


def backfill_assignment_state(apps, schema_editor):
    Appointment = apps.get_model("appointments", "Appointment")
    for appointment in Appointment.objects.filter(physiotherapist__isnull=False).iterator():
        appointment.assignment_status = "PENDING"
        appointment.assigned_by_id = appointment.updated_by_id
        appointment.assigned_at = appointment.updated_at
        appointment.save(update_fields=("assignment_status", "assigned_by", "assigned_at"))


def reverse_assignment_state(apps, schema_editor):
    Appointment = apps.get_model("appointments", "Appointment")
    Appointment.objects.filter(assignment_status="PENDING").update(
        assignment_status="UNASSIGNED",
        assigned_by=None,
        assigned_at=None,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("appointments", "0005_appointment_assigned_at_appointment_assigned_by_and_more")
    ]

    operations = [
        migrations.RunPython(backfill_assignment_state, reverse_assignment_state),
    ]
