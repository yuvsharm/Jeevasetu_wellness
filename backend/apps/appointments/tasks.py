from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentReminder


REMINDER_KINDS = {
    24: AppointmentReminder.Kind.HOURS_24,
    2: AppointmentReminder.Kind.HOURS_2,
}


@transaction.atomic
def reconcile_appointment_reminders(appointment):
    AppointmentReminder.objects.select_for_update().filter(
        appointment=appointment, status=AppointmentReminder.Status.PENDING
    ).update(status=AppointmentReminder.Status.CANCELLED)
    if (
        appointment.status != Appointment.Status.CONFIRMED
        or appointment.assignment_status != Appointment.AssignmentStatus.ACCEPTED
        or appointment.physiotherapist_id is None
    ):
        return []
    now = timezone.now()
    reminders = []
    for hours in settings.APPOINTMENT_REMINDER_OFFSETS_HOURS:
        kind = REMINDER_KINDS.get(hours)
        scheduled_for = appointment.scheduled_start - timedelta(hours=hours)
        if kind is None or scheduled_for <= now:
            continue
        reminder, _ = AppointmentReminder.objects.update_or_create(
            appointment=appointment,
            kind=kind,
            defaults={
                "practitioner": appointment.physiotherapist,
                "scheduled_for": scheduled_for,
                "status": AppointmentReminder.Status.PENDING,
                "sent_at": None,
            },
        )
        reminders.append(reminder)
    return reminders


@shared_task
def dispatch_due_appointment_reminders():
    now = timezone.now()
    due_ids = list(
        AppointmentReminder.objects.filter(
            status=AppointmentReminder.Status.PENDING,
            scheduled_for__lte=now,
            appointment__status=Appointment.Status.CONFIRMED,
            appointment__assignment_status=Appointment.AssignmentStatus.ACCEPTED,
            appointment__scheduled_start__gt=now,
        ).values_list("id", flat=True)[:200]
    )
    sent = 0
    for reminder_id in due_ids:
        with transaction.atomic():
            reminder = AppointmentReminder.objects.select_for_update().filter(
                pk=reminder_id, status=AppointmentReminder.Status.PENDING
            ).first()
            if reminder is None:
                continue
            reminder.status = AppointmentReminder.Status.SENT
            reminder.sent_at = now
            reminder.save(update_fields=("status", "sent_at", "updated_at"))
            sent += 1
    return sent
