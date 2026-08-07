from datetime import timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment
from apps.appointments.models import Appointment, AppointmentAuditEvent, ClinicOperatingHours
from apps.availability.services import ensure_physiotherapist_available
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


def ensure_practitioner_operationally_eligible(physiotherapist):
    profile = getattr(physiotherapist, "practitioner_profile", None)
    # Staff approved before Phase 4B remain operational; all new enrollment profiles are gated.
    if profile is not None and (not profile.is_approved or not profile.is_open_to_work):
        raise ValidationError("The Physiotherapist is not open to new assignments.")


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
    if appointment.physiotherapist is not None:
        ensure_practitioner_operationally_eligible(appointment.physiotherapist)
        ensure_physiotherapist_available(
            physiotherapist=appointment.physiotherapist,
            clinic=appointment.clinic,
            start=appointment.scheduled_start,
            end=appointment.scheduled_end,
            exclude_id=appointment.pk,
        )
        if appointment.assignment_status == Appointment.AssignmentStatus.UNASSIGNED:
            appointment.assignment_status = Appointment.AssignmentStatus.PENDING
            appointment.assigned_by = actor
            appointment.assigned_at = timezone.now()
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
    from apps.appointments.visit_verification import invalidate_active_visit_verifications

    invalidate_active_visit_verifications(appointment, reason="ASSIGNMENT_CHANGED", actor=actor)
    ensure_practitioner_operationally_eligible(physiotherapist)
    ensure_no_overlap(
        physiotherapist=physiotherapist,
        start=appointment.scheduled_start,
        end=appointment.scheduled_end,
        exclude_id=appointment.pk,
    )
    ensure_physiotherapist_available(
        physiotherapist=physiotherapist,
        clinic=appointment.clinic,
        start=appointment.scheduled_start,
        end=appointment.scheduled_end,
        exclude_id=appointment.pk,
    )
    appointment.physiotherapist = physiotherapist
    appointment.assignment_status = Appointment.AssignmentStatus.PENDING
    appointment.assigned_by = actor
    appointment.assigned_at = timezone.now()
    appointment.assignment_responded_at = None
    appointment.assignment_rejection_reason = ""
    appointment.updated_by = actor
    appointment.full_clean()
    appointment.save(
        update_fields=(
            "physiotherapist",
            "assignment_status",
            "assigned_by",
            "assigned_at",
            "assignment_responded_at",
            "assignment_rejection_reason",
            "updated_by",
            "updated_at",
        )
    )
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
def unassign_physiotherapist(appointment, *, actor, reason):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if (
        appointment.status in Appointment.FINAL_STATUSES
        or appointment.status == Appointment.Status.IN_PROGRESS
    ):
        raise ValidationError("This assignment can no longer be cancelled.")
    if appointment.physiotherapist is None:
        raise ValidationError("This appointment is already unassigned.")
    previous = appointment.physiotherapist
    from apps.appointments.visit_verification import invalidate_active_visit_verifications

    invalidate_active_visit_verifications(appointment, reason="ASSIGNMENT_REMOVED", actor=actor)
    appointment.physiotherapist = None
    appointment.assignment_status = Appointment.AssignmentStatus.UNASSIGNED
    appointment.assigned_by = actor
    appointment.assignment_responded_at = None
    appointment.assignment_rejection_reason = ""
    appointment.updated_by = actor
    appointment.save(
        update_fields=(
            "physiotherapist",
            "assignment_status",
            "assigned_by",
            "assignment_responded_at",
            "assignment_rejection_reason",
            "updated_by",
            "updated_at",
        )
    )
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=AppointmentAuditEvent.Event.UNASSIGNED,
        previous_physiotherapist=previous,
        reason=reason.strip()[:255],
    )
    return appointment


@transaction.atomic
def respond_to_assignment(appointment, *, actor, accept, reason=""):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if appointment.physiotherapist_id is None or appointment.physiotherapist.user_id != actor.id:
        raise ValidationError("This assignment is unavailable.")
    if appointment.assignment_status != Appointment.AssignmentStatus.PENDING:
        raise ValidationError("This assignment has already been answered.")
    if not accept and len(reason.strip()) < 3:
        raise ValidationError("A short rejection reason is required.")
    if not accept:
        from apps.appointments.visit_verification import invalidate_active_visit_verifications

        invalidate_active_visit_verifications(
            appointment, reason="ASSIGNMENT_REJECTED", actor=actor
        )
    appointment.assignment_status = (
        Appointment.AssignmentStatus.ACCEPTED if accept else Appointment.AssignmentStatus.REJECTED
    )
    appointment.assignment_responded_at = timezone.now()
    appointment.assignment_rejection_reason = "" if accept else reason.strip()[:255]
    appointment.updated_by = actor
    appointment.save(
        update_fields=(
            "assignment_status",
            "assignment_responded_at",
            "assignment_rejection_reason",
            "updated_by",
            "updated_at",
        )
    )
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=(
            AppointmentAuditEvent.Event.ASSIGNMENT_ACCEPTED
            if accept
            else AppointmentAuditEvent.Event.ASSIGNMENT_REJECTED
        ),
        new_physiotherapist=appointment.physiotherapist,
        reason=appointment.assignment_rejection_reason,
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
        ensure_physiotherapist_available(
            physiotherapist=appointment.physiotherapist,
            clinic=appointment.clinic,
            start=appointment.scheduled_start,
            end=appointment.scheduled_end,
            exclude_id=appointment.pk,
        )
    if new_status == Appointment.Status.IN_PROGRESS:
        from apps.appointments.visit_verification import can_start_visit

        if not can_start_visit(appointment):
            raise ValidationError("Customer arrival verification is required before visit start.")
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


CHANGEABLE_STATUSES = (
    Appointment.Status.DRAFT,
    Appointment.Status.PENDING_ASSIGNMENT,
    Appointment.Status.SCHEDULED,
    Appointment.Status.CONFIRMED,
)


def record_rejected_lifecycle_action(appointment, *, actor, event, code):
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=event,
        outcome=AppointmentAuditEvent.Outcome.REJECTED,
        rejection_code=code,
    )


def _policy_error(message, code):
    return ValidationError(message, code=code)


def _error_code(error):
    if hasattr(error, "error_list") and error.error_list:
        return error.error_list[0].code or "VALIDATION_FAILED"
    return "VALIDATION_FAILED"


def reschedule_appointment(
    appointment,
    *,
    scheduled_start,
    duration_minutes,
    actor,
    allow_override=False,
    override_reason="",
):
    try:
        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .select_related("clinic__organization")
                .get(pk=appointment.pk)
            )
            policy = ClinicOperatingHours.objects.filter(
                clinic=appointment.clinic, is_active=True
            ).first()
            if policy is None:
                raise _policy_error(
                    "Clinic operating hours have not been configured.", "POLICY_UNAVAILABLE"
                )
            if appointment.status not in CHANGEABLE_STATUSES:
                raise _policy_error(
                    "This appointment cannot be rescheduled.", "STATUS_NOT_RESCHEDULABLE"
                )
            now = timezone.now()
            cutoff_breached = appointment.scheduled_start < now + timedelta(
                minutes=policy.rescheduling_cutoff_minutes
            )
            limit_breached = appointment.reschedule_count >= policy.maximum_reschedules
            override_needed = cutoff_breached or limit_breached
            if allow_override and not override_needed:
                raise _policy_error(
                    "A policy override is not required for this appointment.",
                    "OVERRIDE_NOT_REQUIRED",
                )
            if override_needed and not allow_override:
                code = "RESCHEDULE_LIMIT_REACHED" if limit_breached else "RESCHEDULE_CUTOFF"
                raise _policy_error(
                    "The appointment rescheduling policy prevents this change.", code
                )
            if override_needed and not override_reason.strip():
                raise _policy_error(
                    "A structured override reason is required.", "OVERRIDE_REASON_REQUIRED"
                )
            if (
                appointment.physiotherapist
                and not RoleAssignment.objects.filter(
                    user=appointment.physiotherapist.user,
                    user__is_active=True,
                    user__is_enabled=True,
                    organization=appointment.organization,
                    clinic=appointment.clinic,
                    role=Role.PHYSIOTHERAPIST,
                    is_active=True,
                    organization_membership__is_active=True,
                    clinic_membership__is_active=True,
                ).exists()
            ):
                raise _policy_error(
                    "The assigned Physiotherapist is unavailable.", "PHYSIOTHERAPIST_INELIGIBLE"
                )
            scheduled_end = validate_schedule(
                clinic=appointment.clinic,
                start=scheduled_start,
                duration_minutes=duration_minutes,
            )
            if appointment.status in Appointment.BLOCKING_STATUSES:
                if appointment.physiotherapist is None:
                    raise _policy_error(
                        "An assigned Physiotherapist is required.", "PHYSIOTHERAPIST_REQUIRED"
                    )
                ensure_no_overlap(
                    physiotherapist=appointment.physiotherapist,
                    start=scheduled_start,
                    end=scheduled_end,
                    exclude_id=appointment.pk,
                )
            if appointment.physiotherapist is not None:
                ensure_physiotherapist_available(
                    physiotherapist=appointment.physiotherapist,
                    clinic=appointment.clinic,
                    start=scheduled_start,
                    end=scheduled_end,
                    exclude_id=appointment.pk,
                )
            previous_start = appointment.scheduled_start
            from apps.appointments.visit_verification import invalidate_active_visit_verifications

            invalidate_active_visit_verifications(
                appointment, reason="APPOINTMENT_RESCHEDULED", actor=actor
            )
            appointment.scheduled_start = scheduled_start
            appointment.scheduled_end = scheduled_end
            appointment.duration_minutes = duration_minutes
            appointment.reschedule_count += 1
            appointment.updated_by = actor
            appointment.full_clean()
            appointment.save(
                update_fields=(
                    "scheduled_start",
                    "scheduled_end",
                    "duration_minutes",
                    "reschedule_count",
                    "updated_by",
                    "updated_at",
                )
            )
            AppointmentAuditEvent.objects.create(
                appointment=appointment,
                organization=appointment.organization,
                actor=actor,
                event=AppointmentAuditEvent.Event.RESCHEDULED,
                previous_start=previous_start,
                new_start=scheduled_start,
                override_used=override_needed,
                override_reason=override_reason.strip()[:255] if override_needed else "",
            )
            return appointment
    except ValidationError as error:
        record_rejected_lifecycle_action(
            appointment,
            actor=actor,
            event=AppointmentAuditEvent.Event.RESCHEDULE_REJECTED,
            code=_error_code(error),
        )
        raise


def cancel_appointment(
    appointment,
    *,
    category,
    reason,
    actor,
    allow_override=False,
    override_reason="",
):
    try:
        with transaction.atomic():
            appointment = (
                Appointment.objects.select_for_update()
                .select_related("clinic")
                .get(pk=appointment.pk)
            )
            policy = ClinicOperatingHours.objects.filter(
                clinic=appointment.clinic, is_active=True
            ).first()
            if policy is None:
                raise _policy_error(
                    "Clinic operating hours have not been configured.", "POLICY_UNAVAILABLE"
                )
            if appointment.status not in CHANGEABLE_STATUSES:
                raise _policy_error(
                    "This appointment cannot be cancelled.", "STATUS_NOT_CANCELLABLE"
                )
            cutoff_breached = appointment.scheduled_start < timezone.now() + timedelta(
                minutes=policy.cancellation_cutoff_minutes
            )
            if allow_override and not cutoff_breached:
                raise _policy_error(
                    "A policy override is not required for this appointment.",
                    "OVERRIDE_NOT_REQUIRED",
                )
            if cutoff_breached and not allow_override:
                raise _policy_error(
                    "The appointment cancellation cutoff has passed.", "CANCELLATION_CUTOFF"
                )
            if cutoff_breached and not override_reason.strip():
                raise _policy_error(
                    "A structured override reason is required.", "OVERRIDE_REASON_REQUIRED"
                )
            previous_status = appointment.status
            from apps.appointments.visit_verification import invalidate_active_visit_verifications

            invalidate_active_visit_verifications(
                appointment, reason="APPOINTMENT_CANCELLED", actor=actor
            )
            appointment.status = Appointment.Status.CANCELLED
            appointment.cancellation_category = category
            appointment.cancellation_reason = reason.strip()[:255]
            appointment.cancelled_at = timezone.now()
            appointment.cancelled_by = actor
            appointment.updated_by = actor
            appointment.full_clean()
            appointment.save(
                update_fields=(
                    "status",
                    "cancellation_category",
                    "cancellation_reason",
                    "cancelled_at",
                    "cancelled_by",
                    "updated_by",
                    "updated_at",
                )
            )
            AppointmentAuditEvent.objects.create(
                appointment=appointment,
                organization=appointment.organization,
                actor=actor,
                event=AppointmentAuditEvent.Event.CANCELLED,
                previous_status=previous_status,
                new_status=Appointment.Status.CANCELLED,
                reason=appointment.cancellation_reason,
                reason_category=category,
                override_used=cutoff_breached,
                override_reason=override_reason.strip()[:255] if cutoff_breached else "",
            )
            return appointment
    except ValidationError as error:
        record_rejected_lifecycle_action(
            appointment,
            actor=actor,
            event=AppointmentAuditEvent.Event.CANCELLATION_REJECTED,
            code=_error_code(error),
        )
        raise
