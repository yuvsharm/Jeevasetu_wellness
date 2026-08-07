from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import connection, transaction
from django.db.models import Q

from apps.availability.models import (
    ApprovalStatus,
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)
from apps.staff.models import StaffProfile


def _zone(clinic):
    return ZoneInfo(clinic.timezone or clinic.organization.timezone or "Asia/Kolkata")


def ensure_physiotherapist_available(*, physiotherapist, clinic, start, end, exclude_id=None):
    profile_query = StaffProfile.objects
    if connection.in_atomic_block:
        profile_query = profile_query.select_for_update()
    profile_query.get(pk=physiotherapist.pk)
    local_start = start.astimezone(_zone(clinic))
    local_end = end.astimezone(_zone(clinic))
    if local_start.date() != local_end.date():
        raise ValidationError("Physiotherapist availability must not cross midnight.")
    unavailable = AvailabilityException.objects.filter(
        physiotherapist=physiotherapist,
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        kind=AvailabilityException.Kind.UNAVAILABLE,
        starts_at__lt=end,
        ends_at__gt=start,
    ).exists()
    if unavailable:
        raise ValidationError("The Physiotherapist is unavailable during this period.")
    additional = AvailabilityException.objects.filter(
        physiotherapist=physiotherapist,
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        kind=AvailabilityException.Kind.ADDITIONAL_AVAILABILITY,
        starts_at__lte=start,
        ends_at__gte=end,
    ).exists()
    regular = AvailabilityRule.objects.filter(
        physiotherapist=physiotherapist,
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        weekday=local_start.weekday(),
        starts_at__lte=local_start.time().replace(tzinfo=None),
        ends_at__gte=local_end.time().replace(tzinfo=None),
        effective_from__lte=local_start.date(),
    ).filter(Q(effective_until__isnull=True) | Q(effective_until__gte=local_start.date()))
    if not additional and not regular.exists():
        raise ValidationError("The Physiotherapist has no approved availability for this period.")


def validate_rule(rule):
    rule.full_clean()
    hours = rule.clinic.appointment_operating_hours
    if (
        rule.weekday not in hours.weekdays
        or rule.starts_at < hours.opens_at
        or rule.ends_at > hours.closes_at
    ):
        raise ValidationError("Availability must remain within clinic operating hours.")
    overlap = AvailabilityRule.objects.filter(
        physiotherapist=rule.physiotherapist,
        weekday=rule.weekday,
        approval_status=ApprovalStatus.APPROVED,
        is_active=True,
        starts_at__lt=rule.ends_at,
        ends_at__gt=rule.starts_at,
    ).exclude(pk=rule.pk)
    if rule.effective_until:
        overlap = overlap.filter(effective_from__lte=rule.effective_until)
    overlap = overlap.filter(
        Q(effective_until__isnull=True) | Q(effective_until__gte=rule.effective_from)
    )
    if overlap.exists():
        raise ValidationError("Approved working windows must not overlap.")


def validate_exception(value):
    value.full_clean()
    if value.kind == AvailabilityException.Kind.ADDITIONAL_AVAILABILITY:
        zone = _zone(value.clinic)
        local_start = value.starts_at.astimezone(zone)
        local_end = value.ends_at.astimezone(zone)
        hours = value.clinic.appointment_operating_hours
        if (
            local_start.date() != local_end.date()
            or local_start.weekday() not in hours.weekdays
            or local_start.time().replace(tzinfo=None) < hours.opens_at
            or local_end.time().replace(tzinfo=None) > hours.closes_at
        ):
            raise ValidationError(
                "Additional availability must remain within clinic operating hours."
            )
    if (
        AvailabilityException.objects.filter(
            physiotherapist=value.physiotherapist,
            kind=value.kind,
            approval_status=ApprovalStatus.APPROVED,
            is_active=True,
            starts_at__lt=value.ends_at,
            ends_at__gt=value.starts_at,
        )
        .exclude(pk=value.pk)
        .exists()
    ):
        raise ValidationError("Approved availability exceptions must not overlap.")


def validate_for_approval(value):
    if isinstance(value, AvailabilityRule):
        validate_rule(value)
        return
    validate_exception(value)
    if value.kind == AvailabilityException.Kind.UNAVAILABLE:
        from apps.appointments.models import Appointment

        if Appointment.objects.filter(
            physiotherapist=value.physiotherapist,
            status__in=Appointment.BLOCKING_STATUSES,
            scheduled_start__lt=value.ends_at,
            scheduled_end__gt=value.starts_at,
        ).exists():
            raise ValidationError(
                "Existing active appointments must be resolved before approving leave."
            )


def record_event(value, *, actor, action, reason="", rejection_code=""):
    AvailabilityAuditEvent.objects.create(
        organization=value.organization,
        clinic=value.clinic,
        actor=actor,
        physiotherapist=value.physiotherapist,
        rule=value if isinstance(value, AvailabilityRule) else None,
        exception=value if isinstance(value, AvailabilityException) else None,
        action=action,
        reason=reason[:255],
        rejection_code=rejection_code,
    )


def review_availability(value, *, actor, approve, reason=""):
    try:
        with transaction.atomic():
            model = type(value)
            value = model.objects.select_for_update().select_related("clinic").get(pk=value.pk)
            StaffProfile.objects.select_for_update().get(pk=value.physiotherapist_id)
            if value.approval_status != ApprovalStatus.PENDING:
                raise ValidationError("Only pending availability can be reviewed.")
            if not approve:
                value.approval_status = ApprovalStatus.REJECTED
                value.is_active = False
                value.reviewed_by = actor
                value.review_reason = reason[:255]
                value.save()
                record_event(
                    value,
                    actor=actor,
                    action=AvailabilityAuditEvent.Action.REJECTED,
                    reason=reason,
                )
                return value
            validate_for_approval(value)
            value.approval_status = ApprovalStatus.APPROVED
            value.is_active = True
            value.reviewed_by = actor
            value.review_reason = reason[:255]
            value.save()
            record_event(
                value,
                actor=actor,
                action=AvailabilityAuditEvent.Action.APPROVED,
                reason=reason,
            )
            return value
    except ValidationError as error:
        record_event(
            value,
            actor=actor,
            action=AvailabilityAuditEvent.Action.APPROVAL_BLOCKED,
            rejection_code=(
                "ACTIVE_APPOINTMENT_CONFLICT"
                if "appointments" in str(error).lower()
                else "AVAILABILITY_POLICY_REJECTED"
            ),
        )
        raise


def discover_slots(*, clinic, therapy, date_from, date_to, physiotherapist=None):
    from apps.appointments.models import Appointment
    from apps.appointments.scheduling import validate_schedule

    profiles = StaffProfile.objects.filter(
        organization=clinic.organization,
        clinic=clinic,
        staff_type="PHYSIOTHERAPIST",
        user__is_active=True,
        user__is_enabled=True,
        user__role_assignments__organization=clinic.organization,
        user__role_assignments__clinic=clinic,
        user__role_assignments__role="PHYSIOTHERAPIST",
        user__role_assignments__is_active=True,
        user__role_assignments__organization_membership__is_active=True,
        user__role_assignments__clinic_membership__is_active=True,
    ).filter(
        Q(practitioner_profile__isnull=True)
        | Q(
            practitioner_profile__is_approved=True,
            practitioner_profile__is_open_to_work=True,
        )
    )
    if physiotherapist:
        profiles = profiles.filter(pk=physiotherapist.pk)
    duration = therapy.default_duration_minutes or 60
    zone = _zone(clinic)
    results = []
    day = date_from
    while day <= date_to and len(results) < 500:
        cursor = datetime.combine(day, clinic.appointment_operating_hours.opens_at, zone)
        closes = datetime.combine(day, clinic.appointment_operating_hours.closes_at, zone)
        while cursor + timedelta(minutes=duration) <= closes and len(results) < 500:
            start = cursor.astimezone(UTC)
            try:
                end = validate_schedule(clinic=clinic, start=start, duration_minutes=duration)
            except ValidationError:
                cursor += timedelta(minutes=15)
                continue
            for profile in profiles:
                try:
                    ensure_physiotherapist_available(
                        physiotherapist=profile, clinic=clinic, start=start, end=end
                    )
                except ValidationError:
                    continue
                if not Appointment.objects.filter(
                    physiotherapist=profile,
                    status__in=Appointment.BLOCKING_STATUSES,
                    scheduled_start__lt=end,
                    scheduled_end__gt=start,
                ).exists():
                    results.append(
                        {
                            "physiotherapist_id": str(profile.id),
                            "physiotherapist_name": profile.user.get_full_name(),
                            "scheduled_start": start,
                            "scheduled_end": end,
                            "duration_minutes": duration,
                        }
                    )
            cursor += timedelta(minutes=15)
        day += timedelta(days=1)
    return results
