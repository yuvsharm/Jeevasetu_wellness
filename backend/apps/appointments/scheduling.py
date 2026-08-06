from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.appointments.models import Appointment, AppointmentAuditEvent, ClinicOperatingHours
from apps.staff.models import StaffProfile


def validate_schedule(*, clinic, start, duration_minutes):
    now = timezone.now()
    if start < now + timedelta(hours=2):
        raise ValidationError("Appointments require at least two hours notice.")
    if start > now + timedelta(days=90):
        raise ValidationError("Appointments cannot be scheduled more than 90 days ahead.")
    if duration_minutes < 30 or duration_minutes > 180:
        raise ValidationError("Appointment duration must be between 30 and 180 minutes.")
    hours = ClinicOperatingHours.objects.filter(clinic=clinic, is_active=True).first()
    if hours is None:
        raise ValidationError("Clinic operating hours have not been configured.")
    zone = ZoneInfo(clinic.timezone or clinic.organization.timezone or "Asia/Kolkata")
    local_start = start.astimezone(zone)
    local_end = local_start + timedelta(minutes=duration_minutes)
    if (
        local_start.weekday() not in hours.weekdays
        or local_start.time().replace(tzinfo=None) < hours.opens_at
        or local_end.time().replace(tzinfo=None) > hours.closes_at
        or local_end.date() != local_start.date()
    ):
        raise ValidationError("The appointment must be within configured clinic operating hours.")
    return start + timedelta(minutes=duration_minutes)


def ensure_no_overlap(*, physiotherapist, start, end, exclude_id=None):
    if physiotherapist is None:
        return
    StaffProfile.objects.select_for_update().get(pk=physiotherapist.pk)
    conflicts = Appointment.objects.filter(
        physiotherapist=physiotherapist,
        status__in=Appointment.BLOCKING_STATUSES,
        scheduled_start__lt=end,
        scheduled_end__gt=start,
    )
    if exclude_id:
        conflicts = conflicts.exclude(pk=exclude_id)
    if conflicts.exists():
        raise ValidationError("The Physiotherapist already has an overlapping appointment.")


@transaction.atomic
def save_scheduled_appointment(appointment, *, actor, event, reason=""):
    appointment.scheduled_end = validate_schedule(
        clinic=appointment.clinic,
        start=appointment.scheduled_start,
        duration_minutes=appointment.duration_minutes,
    )
    if appointment.status in Appointment.BLOCKING_STATUSES:
        if appointment.physiotherapist is None:
            raise ValidationError("A scheduled appointment requires a Physiotherapist.")
        ensure_no_overlap(
            physiotherapist=appointment.physiotherapist,
            start=appointment.scheduled_start,
            end=appointment.scheduled_end,
            exclude_id=appointment.pk,
        )
    appointment.full_clean()
    appointment.save()
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=event,
        new_status=appointment.status,
        new_start=appointment.scheduled_start,
        new_physiotherapist=appointment.physiotherapist,
        reason=reason,
    )
    return appointment


@transaction.atomic
def assign_physiotherapist(appointment, *, physiotherapist, actor, reason=""):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if (
        appointment.status in Appointment.FINAL_STATUSES
        or appointment.status == Appointment.Status.IN_PROGRESS
    ):
        raise ValidationError("This appointment can no longer be assigned or reassigned.")
    previous = appointment.physiotherapist
    ensure_no_overlap(
        physiotherapist=physiotherapist,
        start=appointment.scheduled_start,
        end=appointment.scheduled_end,
        exclude_id=appointment.pk,
    )
    appointment.physiotherapist = physiotherapist
    appointment.updated_by = actor
    appointment.full_clean()
    appointment.save(update_fields=("physiotherapist", "updated_by", "updated_at"))
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=(
            AppointmentAuditEvent.Event.REASSIGNED
            if previous
            else AppointmentAuditEvent.Event.ASSIGNED
        ),
        previous_physiotherapist=previous,
        new_physiotherapist=physiotherapist,
        reason=reason,
    )
    return appointment


@transaction.atomic
def transition_status(appointment, *, new_status, actor, reason=""):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    allowed = Appointment.TRANSITIONS.get(appointment.status, ())
    if new_status not in allowed:
        raise ValidationError("This appointment status transition is not permitted.")
    if new_status in (Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED):
        if appointment.physiotherapist is None:
            raise ValidationError("An assigned Physiotherapist is required for this status.")
        ensure_no_overlap(
            physiotherapist=appointment.physiotherapist,
            start=appointment.scheduled_start,
            end=appointment.scheduled_end,
            exclude_id=appointment.pk,
        )
    previous = appointment.status
    appointment.status = new_status
    appointment.updated_by = actor
    appointment.full_clean()
    appointment.save(update_fields=("status", "updated_by", "updated_at"))
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=AppointmentAuditEvent.Event.STATUS_CHANGED,
        previous_status=previous,
        new_status=new_status,
        reason=reason,
    )
    return appointment
