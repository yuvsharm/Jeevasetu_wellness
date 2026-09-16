from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentPayment,
    AppointmentRequest,
    AppointmentRequestAuditEvent,
    ClinicOperatingHours,
)
from apps.availability.services import ensure_physiotherapist_available
from apps.staff.models import ServiceArea, StaffProfile


def _normalize_service_area_name(value):
    return " ".join((value or "").split()).casefold()


def _request_service_area_ids(source):
    """Resolve an address snapshot to configured service areas for its organization."""
    city = _normalize_service_area_name(source.city)
    pin_code = (source.pin_code or "").strip()
    matches = set()
    for area in ServiceArea.objects.filter(
        organization_id=source.organization_id, is_active=True
    ).only("id", "name", "pin_codes"):
        normalized_pins = {str(value).strip() for value in area.pin_codes if value}
        if (city and _normalize_service_area_name(area.name) == city) or (
            pin_code and pin_code in normalized_pins
        ):
            matches.add(area.id)
    return matches


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
    required_ids = {
        source.therapy_id,
        *source.requested_therapies.values_list("id", flat=True),
    }
    current_ids = set(
        physiotherapist.therapy_competencies.filter(id__in=required_ids).values_list(
            "id", flat=True
        )
    )
    missing_ids = required_ids - current_ids
    if missing_ids:
        from apps.appointments.models import TherapyOption
        missing = ", ".join(
            TherapyOption.objects.filter(id__in=missing_ids).order_by("name").values_list("name", flat=True)
        )
        raise ValidationError(f"Therapist does not currently offer {missing}.")
    therapist_service_area_ids = set(
        physiotherapist.service_areas.filter(is_active=True).values_list("id", flat=True)
    )
    if (
        therapist_service_area_ids
        and not therapist_service_area_ids.intersection(_request_service_area_ids(source))
    ):
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
        "organization", "creator", "patient_profile", "therapy", "family_member", "selected_package", "selected_offer"
    ).get(pk=source.pk)
    previous_status = source.status
    if action == "REJECT":
        if source.status != AppointmentRequest.Status.PENDING:
            raise ValidationError("Only a pending appointment request can be rejected.")
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

    if action == "ACCEPT":
        if source.status != AppointmentRequest.Status.PENDING:
            raise ValidationError("This appointment request has already been accepted.")
        source.status = AppointmentRequest.Status.APPROVED
        source.save(update_fields=("status", "updated_at"))
        AppointmentRequestAuditEvent.objects.create(
            appointment_request=source,
            organization=source.organization,
            actor=actor,
            event=AppointmentRequestAuditEvent.Event.ACCEPTED,
            previous_status=previous_status,
            new_status=source.status,
        )
        return source, None

    if action not in ("ASSIGN", "ACCEPT_ASSIGN"):
        raise ValidationError("Select a supported appointment request action.")
    if action == "ACCEPT_ASSIGN" and source.status == AppointmentRequest.Status.PENDING:
        source.status = AppointmentRequest.Status.APPROVED
        source.save(update_fields=("status", "updated_at"))
    elif source.status != AppointmentRequest.Status.APPROVED:
        raise ValidationError("Accept this appointment request before assigning a therapist.")
    try:
        return source, source.operational_appointment
    except Appointment.DoesNotExist:
        pass

    patient = source.patient_profile
    if patient is None and source.creator_id is not None:
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
        city=source.city, region=source.region, pin_code=source.pin_code,
        service_latitude=source.latitude, service_longitude=source.longitude,
        service_location_accuracy_meters=source.location_accuracy_meters,
        service_location_source=source.location_source,
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
    from apps.appointments.notification_events import notify_assignment

    notify_assignment(appointment)
    return source, appointment


@transaction.atomic
def rebook_closed_appointment(
    appointment, *, preferred_date, preferred_time, physiotherapist, actor
):
    appointment = Appointment.objects.select_for_update().select_related(
        "originating_request", "patient", "clinic"
    ).get(pk=appointment.pk)
    if (
        appointment.status not in Appointment.FINAL_STATUSES
        and appointment.scheduled_end >= timezone.now()
    ):
        raise ValidationError("Only a closed or past appointment can be booked again.")
    source = appointment.originating_request
    if source is None:
        raise ValidationError("Use Book for Customer for this direct operational appointment.")
    therapy_ids = [source.therapy_id, *source.requested_therapies.values_list("id", flat=True)]
    start = datetime.combine(
        preferred_date,
        preferred_time,
        ZoneInfo(appointment.clinic.timezone or appointment.organization.timezone or "Asia/Kolkata"),
    )
    from apps.appointments.commercial import calculate_quote

    quote = calculate_quote(
        organization=appointment.organization,
        therapy_ids=therapy_ids,
        family_member=source.family_member,
        at=start,
    )
    repeated = AppointmentRequest.objects.create(
        organization=appointment.organization,
        creator=source.creator,
        patient_profile=appointment.patient,
        family_member=source.family_member,
        therapy=source.therapy,
        selected_offer_id=quote.offer_id,
        selected_package_id=quote.package_id,
        commercial_snapshot=quote.snapshot(),
        regular_amount=quote.regular_amount,
        discount_amount=quote.discount_amount,
        final_amount=quote.final_amount,
        patient_name=source.patient_name,
        age=source.age,
        gender=source.gender,
        mobile_number=appointment.patient.mobile_number,
        alternate_mobile=source.alternate_mobile,
        email=appointment.patient.email or source.email,
        session_preference=AppointmentRequest.SessionPreference.SINGLE,
        preferred_date=preferred_date,
        preferred_time=preferred_time,
        problem_description=source.problem_description,
        pain_area=source.pain_area,
        problem_duration=source.problem_duration,
        doctor_reference=source.doctor_reference,
        address=", ".join(filter(None, (appointment.address_line_1, appointment.address_line_2))),
        city=appointment.city,
        region=appointment.region,
        pin_code=appointment.pin_code,
        landmark=appointment.landmark,
        latitude=appointment.service_latitude,
        longitude=appointment.service_longitude,
        location_accuracy_meters=appointment.service_location_accuracy_meters,
        location_source=appointment.service_location_source,
    )
    repeated.requested_therapies.set(source.requested_therapies.all())
    _, new_appointment = decide_appointment_request(
        repeated,
        actor=actor,
        action="ACCEPT_ASSIGN",
        physiotherapist=physiotherapist,
    )
    for value in (appointment, new_appointment):
        AppointmentAuditEvent.objects.create(
            appointment=value,
            organization=value.organization,
            actor=actor,
            event=AppointmentAuditEvent.Event.REBOOKED,
            new_status=new_appointment.status,
            new_start=new_appointment.scheduled_start,
            new_physiotherapist=new_appointment.physiotherapist,
            reason="A new appointment was created from a prior closed appointment.",
        )
    return new_appointment


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
    if appointment.physiotherapist_id and appointment.assigned_at:
        from apps.appointments.notification_events import notify_assignment

        notify_assignment(appointment)
    return appointment


@transaction.atomic
def assign_physiotherapist(
    appointment, *, physiotherapist, actor, reason="", expected_updated_at=None
):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if expected_updated_at and appointment.updated_at != expected_updated_at:
        raise ValidationError("This appointment changed. Refresh it before assigning a therapist.")
    if (
        appointment.status in Appointment.FINAL_STATUSES
        or appointment.status == Appointment.Status.IN_PROGRESS
    ):
        raise ValidationError("This appointment can no longer be assigned or reassigned.")
    previous = appointment.physiotherapist
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
    from apps.appointments.notification_events import notify_assignment

    notify_assignment(appointment)
    return appointment


@transaction.atomic
def unassign_physiotherapist(appointment, *, actor, reason, expected_updated_at=None):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if expected_updated_at and appointment.updated_at != expected_updated_at:
        raise ValidationError("This appointment changed. Refresh it before removing the therapist.")
    if (
        appointment.status in Appointment.FINAL_STATUSES
        or appointment.status == Appointment.Status.IN_PROGRESS
    ):
        raise ValidationError("This assignment can no longer be cancelled.")
    if appointment.physiotherapist is None:
        raise ValidationError("This appointment is already unassigned.")
    previous = appointment.physiotherapist
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
    from apps.appointments.notification_events import notify_unassigned

    notify_unassigned(appointment, previous_physiotherapist=previous)
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
    from apps.appointments.notification_events import notify_assignment_response

    notify_assignment_response(appointment, accepted=accept)
    return appointment


@transaction.atomic
def update_journey(appointment, *, actor, journey_status):
    appointment = Appointment.objects.select_for_update().get(pk=appointment.pk)
    if appointment.physiotherapist_id is None or appointment.physiotherapist.user_id != actor.id:
        raise ValidationError("This visit is unavailable.")
    if appointment.assignment_status != Appointment.AssignmentStatus.ACCEPTED:
        raise ValidationError("Accept the service request before updating the journey.")
    if appointment.status != Appointment.Status.CONFIRMED:
        raise ValidationError("Journey updates are unavailable for this visit.")
    allowed = {
        Appointment.JourneyStatus.NOT_STARTED: (Appointment.JourneyStatus.EN_ROUTE,),
        Appointment.JourneyStatus.EN_ROUTE: (Appointment.JourneyStatus.REACHED,),
        Appointment.JourneyStatus.REACHED: (),
    }
    if journey_status not in allowed[appointment.journey_status]:
        raise ValidationError("This journey transition is not permitted.")
    now = timezone.now()
    appointment.journey_status = journey_status
    fields = ["journey_status", "updated_at"]
    if journey_status == Appointment.JourneyStatus.EN_ROUTE:
        appointment.en_route_at = now
        fields.append("en_route_at")
    else:
        appointment.arrived_at = now
        fields.append("arrived_at")
    appointment.save(update_fields=fields)
    AppointmentAuditEvent.objects.create(appointment=appointment, organization=appointment.organization, actor=actor, event=AppointmentAuditEvent.Event.JOURNEY_STATUS_CHANGED, reason=journey_status)
    if journey_status == Appointment.JourneyStatus.REACHED:
        from apps.appointments.notification_events import notify_reached

        notify_reached(appointment)
    return appointment

@transaction.atomic
def transition_status(appointment, *, new_status, actor, reason="", emit_notification=True):
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
        if appointment.assignment_status != Appointment.AssignmentStatus.ACCEPTED:
            raise ValidationError("The Physiotherapist must accept this appointment first.")
        if appointment.journey_status != Appointment.JourneyStatus.REACHED:
            raise ValidationError("Mark the appointment Reached before starting the session.")
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
    if new_status == Appointment.Status.COMPLETED:
        source = appointment.originating_request
        amount_due = source.final_amount if source and source.final_amount is not None else 0
        AppointmentPayment.objects.get_or_create(
            appointment=appointment,
            defaults={
                "organization": appointment.organization,
                "amount_due": amount_due,
                "updated_by": actor,
            },
        )
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=AppointmentAuditEvent.Event.STATUS_CHANGED,
        previous_status=previous,
        new_status=new_status,
        reason=reason,
    )
    from apps.appointments.notification_events import notify_status_transition

    if emit_notification:
        notify_status_transition(appointment, new_status=new_status)
    return appointment


@transaction.atomic
def complete_and_confirm_payment(appointment, *, actor):
    appointment = (
        Appointment.objects.select_for_update()
        .select_related("physiotherapist__user", "originating_request")
        .get(pk=appointment.pk)
    )
    if appointment.physiotherapist_id is None or appointment.physiotherapist.user_id != actor.id:
        raise ValidationError("This appointment is unavailable.")
    if appointment.assignment_status != Appointment.AssignmentStatus.ACCEPTED:
        raise ValidationError("Accept the service request before completing it.")
    if appointment.status == Appointment.Status.COMPLETED:
        raise ValidationError("This appointment has already been completed.")
    if appointment.status != Appointment.Status.IN_PROGRESS:
        raise ValidationError("Start the therapy before confirming completion and payment.")

    appointment = transition_status(
        appointment,
        new_status=Appointment.Status.COMPLETED,
        actor=actor,
        reason="Therapy delivered and customer payment confirmation verified.",
        emit_notification=False,
    )
    payment = AppointmentPayment.objects.select_for_update().get(appointment=appointment)
    if payment.status == AppointmentPayment.Status.PAID:
        raise ValidationError("Payment has already been confirmed.")
    previous_status = payment.status
    payment.status = AppointmentPayment.Status.PAID
    payment.paid_at = timezone.now()
    payment.updated_by = actor
    payment.save(update_fields=("status", "paid_at", "updated_by", "updated_at"))
    AppointmentAuditEvent.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        actor=actor,
        event=AppointmentAuditEvent.Event.PAYMENT_STATUS_CHANGED,
        previous_status=previous_status,
        new_status=payment.status,
        reason="Customer showed successful owner payment confirmation.",
    )
    from apps.appointments.notification_events import notify_completion_and_payment

    notify_completion_and_payment(appointment)
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
            from apps.appointments.notification_events import notify_rescheduled

            notify_rescheduled(appointment)
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
            from apps.appointments.notification_events import notify_cancelled

            notify_cancelled(appointment)
            return appointment
    except ValidationError as error:
        record_rejected_lifecycle_action(
            appointment,
            actor=actor,
            event=AppointmentAuditEvent.Event.CANCELLATION_REJECTED,
            code=_error_code(error),
        )
        raise
