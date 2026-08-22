import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role
from apps.accounts.permissions import active_roles
from apps.appointments.models import (
    Appointment,
    VisitVerification,
    VisitVerificationAuditEvent,
)

ACTIVE_APPOINTMENT_STATUSES = (Appointment.Status.CONFIRMED,)


@dataclass(frozen=True)
class VisitOtpDelivery:
    """One-time delivery result; the plaintext value is never persisted."""

    otp: str
    expires_at: object


class PortalVisitOtpDelivery:
    """Authenticated portal delivery adapter; provider adapters can replace this later."""

    @staticmethod
    def deliver(otp, verification):
        return VisitOtpDelivery(otp=otp, expires_at=verification.expires_at)


def _audit(verification, *, event, actor=None, outcome="", reason_code=""):
    return VisitVerificationAuditEvent.objects.create(
        verification=verification,
        organization=verification.organization,
        actor=actor,
        event=event,
        outcome=outcome[:16],
        reason_code=reason_code[:48],
    )


def _customer_is_active(appointment):
    customer = appointment.originating_request.creator if appointment.originating_request_id else appointment.patient.user
    return bool(
        customer
        and active_roles(customer, appointment.organization).filter(role=Role.CUSTOMER).exists()
    )


def _physiotherapist_is_active(appointment):
    if appointment.physiotherapist is None:
        return False
    return (
        active_roles(
            appointment.physiotherapist.user, appointment.organization, clinic=appointment.clinic
        )
        .filter(role=Role.PHYSIOTHERAPIST)
        .exists()
    )


def visit_verification_eligibility(appointment, *, at=None):
    now = at or timezone.now()
    if appointment.status not in ACTIVE_APPOINTMENT_STATUSES:
        return False, "APPOINTMENT_NOT_ACTIVE"
    if appointment.physiotherapist_id is None:
        return False, "PHYSIOTHERAPIST_UNASSIGNED"
    if appointment.assignment_status != Appointment.AssignmentStatus.ACCEPTED:
        return False, "ASSIGNMENT_NOT_ACCEPTED"
    if not _customer_is_active(appointment):
        return False, "CUSTOMER_ACCESS_INACTIVE"
    if not _physiotherapist_is_active(appointment):
        return False, "PHYSIOTHERAPIST_ACCESS_INACTIVE"
    opens_at = appointment.scheduled_start - timedelta(
        minutes=settings.VISIT_OTP_WINDOW_BEFORE_MINUTES
    )
    closes_at = appointment.scheduled_start + timedelta(
        minutes=settings.VISIT_OTP_WINDOW_AFTER_MINUTES
    )
    if now < opens_at or now > closes_at:
        return False, "OUTSIDE_VERIFICATION_WINDOW"
    return True, "ELIGIBLE"


def _expire_if_needed(verification, *, actor=None, at=None):
    now = at or timezone.now()
    if verification.state == VisitVerification.State.AWAITING and now >= verification.expires_at:
        verification.state = VisitVerification.State.EXPIRED
        verification.save(update_fields=("state", "updated_at"))
        _audit(
            verification,
            event=VisitVerificationAuditEvent.Event.EXPIRED,
            actor=actor,
            reason_code="OTP_EXPIRED",
        )
    return verification


def latest_visit_verification(appointment, *, actor=None):
    verification = appointment.visit_verifications.order_by("-created_at").first()
    if verification:
        _expire_if_needed(verification, actor=actor)
    return verification


@transaction.atomic
def issue_visit_otp(appointment, *, customer, delivery=None):
    appointment = (
        Appointment.objects.select_for_update(of=("self",))
        .select_related(
            "organization",
            "clinic",
            "patient__user",
            "physiotherapist__user",
        )
        .get(pk=appointment.pk)
    )
    owner_id = appointment.originating_request.creator_id if appointment.originating_request_id else appointment.patient.user_id
    if owner_id != customer.id:
        raise ValidationError("Visit verification is unavailable.")
    eligible, code = visit_verification_eligibility(appointment)
    if not eligible:
        raise ValidationError("Visit OTP is not currently available.", code=code)
    previous = (
        VisitVerification.objects.select_for_update()
        .filter(appointment=appointment, state=VisitVerification.State.AWAITING)
        .first()
    )
    event = VisitVerificationAuditEvent.Event.ISSUED
    if previous:
        previous.state = VisitVerification.State.INVALIDATED
        previous.invalidated_at = timezone.now()
        previous.invalidation_reason = "CUSTOMER_REISSUED"
        previous.save(
            update_fields=(
                "state",
                "invalidated_at",
                "invalidation_reason",
                "updated_at",
            )
        )
        _audit(
            previous,
            event=VisitVerificationAuditEvent.Event.INVALIDATED,
            actor=customer,
            reason_code="CUSTOMER_REISSUED",
        )
        event = VisitVerificationAuditEvent.Event.REISSUED
    otp = f"{secrets.randbelow(1_000_000):06d}"
    now = timezone.now()
    window_close = appointment.scheduled_start + timedelta(
        minutes=settings.VISIT_OTP_WINDOW_AFTER_MINUTES
    )
    verification = VisitVerification.objects.create(
        appointment=appointment,
        organization=appointment.organization,
        customer=customer,
        physiotherapist=appointment.physiotherapist,
        otp_hash=make_password(otp, hasher="pbkdf2_sha256"),
        issued_at=now,
        expires_at=min(now + timedelta(minutes=settings.VISIT_OTP_EXPIRY_MINUTES), window_close),
        max_attempts=settings.VISIT_OTP_MAX_ATTEMPTS,
    )
    _audit(verification, event=event, actor=customer, outcome="SUCCEEDED")
    adapter = delivery or PortalVisitOtpDelivery()
    return verification, adapter.deliver(otp, verification)


def _check_rate_limit(verification, actor):
    key = f"visit-otp-attempt:{verification.id}:{actor.id}"
    if cache.add(key, 1, timeout=settings.VISIT_OTP_RATE_LIMIT_WINDOW_SECONDS):
        attempts = 1
    else:
        try:
            attempts = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=settings.VISIT_OTP_RATE_LIMIT_WINDOW_SECONDS)
            attempts = 1
    if attempts > settings.VISIT_OTP_RATE_LIMIT_ATTEMPTS:
        raise ValidationError("Too many verification requests. Please try again later.")


def verify_visit_otp(appointment, *, physiotherapist_user, otp):
    error_message = None
    error_code = None
    with transaction.atomic():
        appointment = (
            Appointment.objects.select_for_update(of=("self",))
            .select_related(
                "organization",
                "clinic",
                "patient__user",
                "physiotherapist__user",
            )
            .get(pk=appointment.pk)
        )
        verification = (
            VisitVerification.objects.select_for_update()
            .filter(appointment=appointment)
            .order_by("-created_at")
            .first()
        )
        if verification is None:
            error_message = "Visit verification is not ready."
        else:
            assigned_user_id = (
                appointment.physiotherapist.user_id if appointment.physiotherapist else None
            )
            assignment_matches = (
                assigned_user_id == physiotherapist_user.id
                and verification.physiotherapist_id == appointment.physiotherapist_id
            )
            if not assignment_matches:
                _audit(
                    verification,
                    event=VisitVerificationAuditEvent.Event.UNAUTHORIZED,
                    actor=physiotherapist_user,
                    outcome="REJECTED",
                    reason_code="ASSIGNMENT_MISMATCH",
                )
                error_message = "Visit verification is unavailable."
            elif not _physiotherapist_is_active(appointment):
                _audit(
                    verification,
                    event=VisitVerificationAuditEvent.Event.UNAUTHORIZED,
                    actor=physiotherapist_user,
                    outcome="REJECTED",
                    reason_code="ACCESS_INACTIVE",
                )
                error_message = "Visit verification is unavailable."
            else:
                _check_rate_limit(verification, physiotherapist_user)
                _expire_if_needed(verification, actor=physiotherapist_user)
                state_errors = {
                    VisitVerification.State.VERIFIED: "This visit has already been verified.",
                    VisitVerification.State.EXPIRED: "The Visit OTP has expired.",
                    VisitVerification.State.LOCKED: (
                        "Too many incorrect attempts. Visit verification is locked."
                    ),
                    VisitVerification.State.INVALIDATED: "This Visit OTP is no longer valid.",
                }
                error_message = state_errors.get(verification.state)
                if error_message is None:
                    eligible, error_code = visit_verification_eligibility(appointment)
                    if not eligible:
                        error_message = "This appointment is not eligible for verification."
                    else:
                        _audit(
                            verification,
                            event=VisitVerificationAuditEvent.Event.ATTEMPTED,
                            actor=physiotherapist_user,
                        )
                        if not check_password(otp, verification.otp_hash):
                            verification.failed_attempt_count += 1
                            fields = ["failed_attempt_count", "updated_at"]
                            if verification.failed_attempt_count >= verification.max_attempts:
                                verification.state = VisitVerification.State.LOCKED
                                verification.locked_at = timezone.now()
                                fields.extend(("state", "locked_at"))
                            verification.save(update_fields=fields)
                            if verification.state == VisitVerification.State.LOCKED:
                                _audit(
                                    verification,
                                    event=VisitVerificationAuditEvent.Event.LOCKED,
                                    actor=physiotherapist_user,
                                    outcome="REJECTED",
                                    reason_code="MAX_ATTEMPTS",
                                )
                            error_message = "The Visit OTP is invalid."
                        else:
                            verification.state = VisitVerification.State.VERIFIED
                            verification.verified_at = timezone.now()
                            verification.save(update_fields=("state", "verified_at", "updated_at"))
                            _audit(
                                verification,
                                event=VisitVerificationAuditEvent.Event.SUCCEEDED,
                                actor=physiotherapist_user,
                                outcome="SUCCEEDED",
                            )
    if error_message:
        raise ValidationError(error_message, code=error_code)
    return verification


@transaction.atomic
def invalidate_active_visit_verifications(appointment, *, reason, actor=None):
    verifications = list(
        VisitVerification.objects.select_for_update().filter(
            appointment=appointment, state=VisitVerification.State.AWAITING
        )
    )
    now = timezone.now()
    for verification in verifications:
        verification.state = VisitVerification.State.INVALIDATED
        verification.invalidated_at = now
        verification.invalidation_reason = reason[:64]
        verification.save(
            update_fields=(
                "state",
                "invalidated_at",
                "invalidation_reason",
                "updated_at",
            )
        )
        _audit(
            verification,
            event=VisitVerificationAuditEvent.Event.INVALIDATED,
            actor=actor,
            reason_code=reason,
        )
    return len(verifications)


def can_start_visit(appointment):
    if appointment.status != Appointment.Status.CONFIRMED:
        return False
    verification = latest_visit_verification(appointment)
    return bool(
        verification
        and verification.state == VisitVerification.State.VERIFIED
        and verification.physiotherapist_id == appointment.physiotherapist_id
        and verification.customer_id == (appointment.originating_request.creator_id if appointment.originating_request_id else appointment.patient.user_id)
        and _customer_is_active(appointment)
        and _physiotherapist_is_active(appointment)
    )


def visit_verification_status(appointment, *, actor=None):
    verification = latest_visit_verification(appointment, actor=actor)
    if verification is None:
        eligible, _ = visit_verification_eligibility(appointment)
        return {
            "status": "AWAITING_VERIFICATION" if eligible else "NOT_READY",
            "verified_at": None,
            "expires_at": None,
            "failed_attempt_warning": False,
        }
    status_map = {
        VisitVerification.State.AWAITING: "AWAITING_VERIFICATION",
        VisitVerification.State.VERIFIED: "VERIFIED",
        VisitVerification.State.EXPIRED: "EXPIRED",
        VisitVerification.State.LOCKED: "LOCKED",
        VisitVerification.State.INVALIDATED: "NOT_READY",
    }
    return {
        "status": status_map[verification.state],
        "verified_at": verification.verified_at,
        "expires_at": (
            verification.expires_at
            if verification.state == VisitVerification.State.AWAITING
            else None
        ),
        "failed_attempt_warning": verification.failed_attempt_count > 0,
    }
