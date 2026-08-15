import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.signing import BadSignature, SignatureExpired, dumps, loads
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from apps.appointments.models import BookingPhoneVerification

TOKEN_SALT = "appointments.booking-phone-verification"


@dataclass(frozen=True)
class BookingOtpMessage:
    mobile_number: str
    otp: str
    expires_at: object


class UnconfiguredBookingOtpDelivery:
    def deliver(self, message):
        raise ImproperlyConfigured(
            "Booking OTP delivery is not configured. Set BOOKING_OTP_DELIVERY_BACKEND to a provider implementation in production."
        )


class DevBookingOtpDelivery:
    def deliver(self, message):
        return BookingOtpMessage(
            mobile_number=message.mobile_number,
            otp=message.otp,
            expires_at=message.expires_at,
        )


def _delivery():
    backend = getattr(
        settings,
        "BOOKING_OTP_DELIVERY_BACKEND",
        "apps.appointments.booking_verification.DevBookingOtpDelivery",
    )
    return import_string(backend)()


def issue_booking_otp_details(*, organization, mobile_number, client_key):
    rate_key = f"booking-otp-send:{organization.id}:{mobile_number}:{client_key}"
    if not cache.add(rate_key, 1, timeout=settings.BOOKING_OTP_RESEND_SECONDS):
        raise ValidationError("Please wait before requesting another OTP.")
    otp = f"{secrets.randbelow(1_000_000):06d}"
    now = timezone.now()
    verification = BookingPhoneVerification.objects.create(
        organization=organization,
        mobile_number=mobile_number,
        otp_hash=make_password(otp, hasher="pbkdf2_sha256"),
        expires_at=now + timedelta(minutes=settings.BOOKING_OTP_EXPIRY_MINUTES),
        max_attempts=settings.BOOKING_OTP_MAX_ATTEMPTS,
    )
    try:
        delivery = _delivery().deliver(BookingOtpMessage(mobile_number, otp, verification.expires_at))
    except Exception:
        verification.delete()
        cache.delete(rate_key)
        raise
    return verification, delivery


def issue_booking_otp(*, organization, mobile_number, client_key):
    verification, _ = issue_booking_otp_details(
        organization=organization,
        mobile_number=mobile_number,
        client_key=client_key,
    )
    return verification


@transaction.atomic
def verify_booking_otp(*, organization, verification_id, mobile_number, otp):
    verification = BookingPhoneVerification.objects.select_for_update().filter(
        id=verification_id, organization=organization, mobile_number=mobile_number
    ).first()
    if not verification or verification.consumed_at or verification.verified_at:
        raise ValidationError("This verification request is invalid.")
    if timezone.now() >= verification.expires_at:
        raise ValidationError("The OTP has expired.")
    if verification.failed_attempt_count >= verification.max_attempts:
        raise ValidationError("Too many incorrect attempts. Request a new OTP.")
    if not check_password(otp, verification.otp_hash):
        verification.failed_attempt_count += 1
        verification.save(update_fields=("failed_attempt_count",))
        raise ValidationError("The OTP is invalid.")
    verification.verified_at = timezone.now()
    verification.save(update_fields=("verified_at",))
    return dumps({"verification_id": str(verification.id), "mobile_number": mobile_number, "organization_id": str(organization.id)}, salt=TOKEN_SALT, compress=True)


def resolve_booking_verification(*, organization, mobile_number, token, lock=False):
    try:
        payload = loads(token, salt=TOKEN_SALT, max_age=settings.BOOKING_OTP_TOKEN_SECONDS)
    except (BadSignature, SignatureExpired) as error:
        raise ValidationError("Please verify your mobile number again.") from error
    if payload.get("mobile_number") != mobile_number or payload.get("organization_id") != str(organization.id):
        raise ValidationError("Mobile verification does not match this booking.")
    queryset = BookingPhoneVerification.objects.select_for_update() if lock else BookingPhoneVerification.objects
    verification = queryset.filter(id=payload.get("verification_id"), organization=organization, mobile_number=mobile_number, verified_at__isnull=False, consumed_at__isnull=True).first()
    if not verification:
        raise ValidationError("Please verify your mobile number again.")
    return verification
