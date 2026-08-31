from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentRequest,
    AppointmentRequestAuditEvent,
    ClinicOperatingHours,
)
from apps.availability.services import ensure_physiotherapist_available
from apps.staff.models import StaffProfile


def validate_schedule(*, clinic, start, duration_minutes):
    hours = ClinicOperatingHours.objects.filter(clinic=clinic, is_active=True).first()
    if hours is None:
        raise ValidationError("Clinic operating hours have not been configured.")
    zone = ZoneInfo(clinic.timezone or clinic.organization.timezone or "Asia/Kolkata")
    local_now = timezone.now().astimezone(zone)
    local_start = start.astimezone(zone)
    if local_start < local_now + timedelta(hours=hours.minimum_advance_notice_hours):
        raise ValidationError(
            f"This appointment requires at least {hours.minimum_advance_notice_hours} hours' advance booking."
        )
    if local_start > local_now + timedelta(days=90):
        raise ValidationError("Appointments cannot be scheduled more than 90 days ahead.")
    if duration_minutes < 30 or duration_minutes > 360:
        raise ValidationError("Appointment duration must be between 30 and 360 minutes.")
    local_end = local_start + timedelta(minutes=duration_minutes)
    window = hours.window_for_weekday(local_start.weekday())
    if (
        window is None
        or local_start.time().replace(tzinfo=None) < window[0]
        or local_end.time().replace(tzinfo=None) > window[1]
        or local_end.date() != local_start.date()
    ):
        raise ValidationError("The appointment must be within configured clinic operating hours.")
    return start + timedelta(minutes=duration_minutes)


def ensure_no_overlap(*, physiotherapist, start, end, exclude_id=None):
    if physiotherapist is None:
        return
    profile_query = StaffProfile.objects
    if connection.in_atomic_block:
        profile_query = profile_query.select_for_update()
    profile_query.get(pk=physiotherapist.pk)
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


def ensure_request_practitioner_eligible(*, source, physiotherapist, start, end):
    if (
        physiotherapist.organization_id != source.organization_id
        or physiotherapist.staff_type != Role.PHYSIOTHERAPIST
        or not RoleAssignment.objects.filter(
            user=physiotherapist.user,
            organization=source.organization,
            clinic=physiotherapist.clinic,
            role=Role.PHYSIOTHERAPIST,
            is_active=True,
            organization_membership__is_active=True,
            clinic_membership__is_active=True,
            user__is_active=True,
            user__is_enabled=True,
        ).exists()
    ):
        raise ValidationError("The selected Physiotherapist is unavailable.")
    ensure_practitioner_operationally_eligible(physiotherapist)
    profile = getattr(physiotherapist, "practitioner_profile", None)
    if profile is not None:
        required_ids = {
            source.therapy_id,
            *source.requested_therapies.values_list("id", flat=True),
        }
        verified_ids = set(
            profile.source_application.competencies.filter(
                therapy_id__in=required_ids, verification_status="VERIFIED"
            ).values_list("therapy_id", flat=True)
        )
        if not required_ids.issubset(verified_ids):
            raise ValidationError("The selected Physiotherapist is missing a required therapy competency.")
    service_areas = list(physiotherapist.service_areas.filter(is_active=True))
    if service_areas and not any(source.pin_code in area.pin_codes for area in service_areas):
        raise ValidationError("The selected Physiotherapist does not serve this area.")
    ensure_no_overlap(physiotherapist=physiotherapist, start=start, end=end)
    ensure_physiotherapist_available(
        physiotherapist=physiotherapist,
        clinic=physiotherapist.clinic,
        start=start,
        end=end,
    )


@transaction.atomic
def decide_appointment_request(
    source, *, actor, action, physiotherapist=None, rejection_category="",
    customer_reason="", internal_note=""
):
    source = AppointmentRequest.objects.select_for_update(of=("self",)).select_related(
        "organization", "creator", "therapy", "family_member", "selected_package", "selected_offer"
    ).get(pk=source.pk)
    if source.status != AppointmentRequest.Status.PENDING:
        raise ValidationError("This appointment request has already been decided.")
    previous_status = source.status
    if action == "REJECT":
        source.status = AppointmentRequest.Status.REJECTED
        source.rejection_category = rejection_category
        source.rejection_customer_reason = customer_reason.strip()
        source.rejection_internal_note = internal_note.strip()
        source.save(update_fields=(
            "status", "rejection_category", "rejection_customer_reason",
            "rejection_internal_note", "updated_at",
        ))
        AppointmentRequestAuditEvent.objects.create(
            appointment_request=source, organization=source.organization, actor=actor,
            event=AppointmentRequestAuditEvent.Event.REJECTED,
            previous_status=previous_status, new_status=source.status,
            reason_category=rejection_category, customer_reason=customer_reason.strip(),
            internal_note=internal_note.strip(),
        )
        return source, None

    if source.creator_id is None:
        raise ValidationError("A customer profile is required before this request can be assigned.")
    patient = source.creator.patient_profiles.filter(
        organization=source.organization, is_active=True
    ).select_related("clinic").first()
    if patient is None:
        raise ValidationError("A customer patient profile is required before assignment.")
    clinic = patient.clinic
    zone = ZoneInfo(clinic.timezone or source.organization.timezone or "Asia/Kolkata")
    start = datetime.combine(source.preferred_date, source.preferred_time, zone)
    end = validate_schedule(
        clinic=clinic, start=start, duration_minutes=source.requested_duration_minutes
    )
    ensure_request_practitioner_eligible(
        source=source, physiotherapist=physiotherapist, start=start, end=end
    )
    from apps.appointments.commercial import calculate_quote

    quote = calculate_quote(
        organization=source.organization,
        therapy_ids=[source.therapy_id, *source.requested_therapies.values_list("id", flat=True)],
        package_id=source.selected_package_id,
        offer_id=source.selected_offer_id,
        family_member=source.family_member,
        at=start,
    )
    source.commercial_snapshot = quote.snapshot()
    source.regular_amount = quote.regular_amount
    source.discount_amount = quote.discount_amount
    source.final_amount = quote.final_amount
    source.status = AppointmentRequest.Status.APPROVED
    source.save(update_fields=(
        "commercial_snapshot", "regular_amount", "discount_amount", "final_amount",
        "status", "updated_at",
    ))
    appointment = Appointment(
        organization=source.organization, clinic=clinic, originating_request=source,
        patient=patient, therapy=source.therapy, physiotherapist=physiotherapist,
        scheduled_start=start, scheduled_end=end, duration_minutes=source.requested_duration_minutes,
        status=Appointment.Status.SCHEDULED,
        address_line_1=source.address[:255], landmark=source.landmark,
        city=source.city, region="Uttar Pradesh", pin_code=source.pin_code,
        assignment_status=Appointment.AssignmentStatus.PENDING,
        assigned_by=actor, assigned_at=timezone.now(), created_by=actor, updated_by=actor,
    )
    appointment.full_clean()
    appointment.save()
    AppointmentAuditEvent.objects.create(
        appointment=appointment, organization=source.organization, actor=actor,
        event=AppointmentAuditEvent.Event.CONVERTED, new_status=appointment.status,
        new_start=start, new_physiotherapist=physiotherapist,
        reason="Approved and assigned from customer request",
    )
    AppointmentRequestAuditEvent.objects.create(
        appointment_request=source, organization=source.organization, actor=actor,
        event=AppointmentRequestAuditEvent.Event.APPROVED_AND_ASSIGNED,
        previous_status=previous_status, new_status=source.status,
        physiotherapist=physiotherapist,
    )
    return source, appointment


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
    if appointment.status in Appointment.FINAL_STATUSES:
        raise ValidationError("This assignment is no longer available.")
    if accept:
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
    if accept and appointment.status == Appointment.Status.SCHEDULED:
        appointment.status = Appointment.Status.CONFIRMED
    appointment.assignment_responded_at = timezone.now()
    appointment.assignment_rejection_reason = "" if accept else reason.strip()[:255]
    appointment.updated_by = actor
    appointment.save(
        update_fields=(
            "assignment_status",
            "assignment_responded_at",
            "assignment_rejection_reason",
            "status",
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
    from apps.appointments.tasks import reconcile_appointment_reminders

    reconcile_appointment_reminders(appointment)
    return appointment


@transaction.atomic
def update_journey(appointment, *, actor, journey_status, latitude=None, longitude=None):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if appointment.physiotherapist_id is None or appointment.physiotherapist.user_id != actor.id:
        raise ValidationError("This visit is unavailable.")
    if appointment.assignment_status != Appointment.AssignmentStatus.ACCEPTED:
        raise ValidationError("Accept the service request before updating the journey.")
    if appointment.status not in (Appointment.Status.SCHEDULED, Appointment.Status.CONFIRMED):
        raise ValidationError("Journey updates are unavailable for this visit.")
    allowed = {Appointment.JourneyStatus.NOT_STARTED: (Appointment.JourneyStatus.EN_ROUTE,), Appointment.JourneyStatus.EN_ROUTE: (Appointment.JourneyStatus.ARRIVED,), Appointment.JourneyStatus.ARRIVED: ()}
    if journey_status not in allowed[appointment.journey_status]:
        raise ValidationError("This journey transition is not permitted.")
    now = timezone.now()
    appointment.journey_status = journey_status
    fields = ["journey_status", "updated_at"]
    if journey_status == Appointment.JourneyStatus.EN_ROUTE:
        appointment.en_route_at = now; fields.append("en_route_at")
    else:
        appointment.arrived_at = now; fields.append("arrived_at")
    if latitude is not None and longitude is not None:
        appointment.shared_latitude = latitude; appointment.shared_longitude = longitude; appointment.location_shared_at = now
        fields.extend(("shared_latitude", "shared_longitude", "location_shared_at"))
    appointment.save(update_fields=fields)
    AppointmentAuditEvent.objects.create(appointment=appointment, organization=appointment.organization, actor=actor, event=AppointmentAuditEvent.Event.JOURNEY_STATUS_CHANGED, reason=journey_status)
    return appointment

@transaction.atomic
def transition_status(appointment, *, new_status, actor, reason=""):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if appointment.status == new_status and new_status == Appointment.Status.COMPLETED:
        return appointment
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
    now = timezone.now()
    timestamp_field = None
    if new_status == Appointment.Status.IN_PROGRESS:
        appointment.service_started_at = now
        timestamp_field = "service_started_at"
    elif new_status == Appointment.Status.COMPLETED:
        appointment.completed_at = now
        timestamp_field = "completed_at"
    appointment.updated_by = actor
    appointment.full_clean()
    update_fields = ["status", "updated_by", "updated_at"]
    if timestamp_field:
        update_fields.append(timestamp_field)
    appointment.save(update_fields=update_fields)
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
            from apps.appointments.tasks import reconcile_appointment_reminders

            reconcile_appointment_reminders(appointment)
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
            from apps.appointments.tasks import reconcile_appointment_reminders

            reconcile_appointment_reminders(appointment)
            return appointment
    except ValidationError as error:
        record_rejected_lifecycle_action(
            appointment,
            actor=actor,
            event=AppointmentAuditEvent.Event.CANCELLATION_REJECTED,
            code=_error_code(error),
        )
        raise
