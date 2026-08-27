import json
import logging
import re
import secrets
import socket
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlsplit

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
logger = logging.getLogger(__name__)
SAFE_PROVIDER_KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")
SENSITIVE_PROVIDER_KEY = re.compile(r"(?i)(auth|key|mobile|identifier|otp|secret|token)")


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


class Msg91VerificationError(Exception):
    """A deliberately non-sensitive MSG91 verification failure."""


def _safe_endpoint_label():
    parsed = urlsplit(settings.MSG91_VERIFY_URL)
    return f"{parsed.hostname or 'unknown'}{parsed.path or '/'}"


def _log_msg91(category, **fields):
    details = " ".join(f"{key}={value}" for key, value in fields.items())
    logger.warning(f"{category}{f' {details}' if details else ''}")


def _is_phone_like(value):
    if not isinstance(value, (str, int)):
        return False
    value = str(value).strip()
    digits = "".join(character for character in value if character.isdigit())
    return 10 <= len(digits) <= 15 and bool(re.fullmatch(r"\+?[0-9][0-9\s().-]*", value))


def _message_kind(payload):
    if "message" not in payload:
        return "absent"
    message = payload["message"]
    if _is_phone_like(message):
        return "phone-like"
    if isinstance(message, str):
        return "status-text"
    if isinstance(message, (dict, list)):
        return "object"
    return "other"


def _safe_provider_type(payload):
    value = payload.get("type")
    if isinstance(value, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,31}", value):
        return value.lower()
    return "other" if value is not None else "absent"


def _safe_top_level_keys(payload):
    return sorted(
        key
        for key in payload
        if isinstance(key, str)
        and SAFE_PROVIDER_KEY.fullmatch(key)
        and not SENSITIVE_PROVIDER_KEY.search(key)
    )


def _network_failure_kind(reason):
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, (ConnectionError, ConnectionRefusedError)):
        return "connection"
    return "other"


def _find_verified_identifier(value):
    if isinstance(value, dict):
        for key in ("mobile", "mobile_number", "identifier"):
            candidate = value.get(key)
            if isinstance(candidate, (str, int)):
                return str(candidate)
        message = value.get("message")
        if isinstance(message, (str, int)):
            if _is_phone_like(message):
                return str(message).strip()
        for child in value.values():
            candidate = _find_verified_identifier(child)
            if candidate:
                return candidate
    elif isinstance(value, list):
        for child in value:
            candidate = _find_verified_identifier(child)
            if candidate:
                return candidate
    return None


def verify_msg91_access_token(*, access_token, mobile_number):
    auth_key = getattr(settings, "MSG91_AUTH_KEY", "")
    if not auth_key:
        raise ImproperlyConfigured("MSG91 server verification is not configured.")
    body = json.dumps({"access-token": access_token}).encode("utf-8")
    request = urllib.request.Request(
        settings.MSG91_VERIFY_URL,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json", "authkey": auth_key},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=settings.MSG91_TIMEOUT_SECONDS) as response:
            if not 200 <= response.status < 300:
                _log_msg91(
                    "msg91_verify_http_error",
                    status=response.status,
                    endpoint=_safe_endpoint_label(),
                )
                raise Msg91VerificationError("MSG91 rejected the verification token.")
            provider_status = response.status
            raw_response = response.read()
    except urllib.error.HTTPError as error:
        _log_msg91("msg91_verify_http_error", status=error.code, endpoint=_safe_endpoint_label())
        raise Msg91VerificationError("Mobile verification is temporarily unavailable.") from error
    except TimeoutError as error:
        _log_msg91("msg91_verify_timeout")
        raise Msg91VerificationError("Mobile verification is temporarily unavailable.") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            _log_msg91("msg91_verify_timeout")
        else:
            _log_msg91("msg91_verify_network_error", kind=_network_failure_kind(error.reason))
        raise Msg91VerificationError("Mobile verification is temporarily unavailable.") from error
    try:
        payload = json.loads(raw_response.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _log_msg91("msg91_verify_invalid_json", status=provider_status)
        raise Msg91VerificationError("Mobile verification is temporarily unavailable.") from error
    if isinstance(payload, dict):
        safe_keys = _safe_top_level_keys(payload)
        _log_msg91(
            "msg91_verify_response",
            status=provider_status,
            provider_type=_safe_provider_type(payload),
            message_kind=_message_kind(payload),
            keys=",".join(safe_keys) if safe_keys else "none",
        )
    else:
        _log_msg91(
            "msg91_verify_response",
            status=provider_status,
            provider_type="absent",
            message_kind="absent",
            keys="none",
        )
    if not isinstance(payload, dict) or str(payload.get("type", "")).lower() not in {"success", "verified"}:
        raise Msg91VerificationError("MSG91 rejected the verification token.")
    identifier = _find_verified_identifier(payload)
    digits = "".join(character for character in (identifier or "") if character.isdigit())
    if not digits or digits[-10:] != mobile_number:
        raise Msg91VerificationError("Mobile verification does not match this request.")


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
    otp = f"{secrets.randbelow(1_000_000):06d}" if not settings.MSG91_ENABLED else None
    now = timezone.now()
    verification = BookingPhoneVerification.objects.create(
        organization=organization,
        mobile_number=mobile_number,
        otp_hash=make_password(otp, hasher="pbkdf2_sha256") if otp else "msg91-widget",
        expires_at=now + timedelta(minutes=settings.BOOKING_OTP_EXPIRY_MINUTES),
        max_attempts=settings.BOOKING_OTP_MAX_ATTEMPTS,
    )
    try:
        delivery = None if settings.MSG91_ENABLED else _delivery().deliver(
            BookingOtpMessage(mobile_number, otp, verification.expires_at)
        )
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


def verify_booking_otp(*, organization, verification_id, mobile_number, otp=None, access_token=None):
    invalid_otp = False
    with transaction.atomic():
        verification = BookingPhoneVerification.objects.select_for_update().filter(
            id=verification_id, organization=organization, mobile_number=mobile_number
        ).first()
        if not verification or verification.consumed_at or verification.verified_at:
            raise ValidationError("This verification request is invalid.")
        if timezone.now() >= verification.expires_at:
            raise ValidationError("The OTP has expired.")
        if verification.failed_attempt_count >= verification.max_attempts:
            raise ValidationError("Too many incorrect attempts. Request a new OTP.")
        provider_error = None
        if settings.MSG91_ENABLED:
            if not access_token:
                raise ValidationError("A verified MSG91 access token is required.")
            try:
                verify_msg91_access_token(access_token=access_token, mobile_number=mobile_number)
                valid = True
            except Msg91VerificationError as error:
                valid = False
                provider_error = str(error)
        else:
            valid = bool(otp) and check_password(otp, verification.otp_hash)
        if not valid:
            verification.failed_attempt_count += 1
            verification.save(update_fields=("failed_attempt_count",))
            invalid_otp = True
        else:
            verification.verified_at = timezone.now()
            verification.save(update_fields=("verified_at",))
    if invalid_otp:
        raise ValidationError(provider_error or "The OTP is invalid.")
    return dumps({"verification_id": str(verification.id), "mobile_number": mobile_number, "organization_id": str(organization.id)}, salt=TOKEN_SALT, compress=True)


def resolve_booking_verification(*, organization, mobile_number, token, lock=False):
    try:
        payload = loads(token, salt=TOKEN_SALT, max_age=settings.BOOKING_OTP_TOKEN_SECONDS)
    except (BadSignature, SignatureExpired) as error:
        raise ValidationError("Please verify your mobile number again.") from error
    if payload.get("mobile_number") != mobile_number or payload.get("organization_id") != str(organization.id):
        raise ValidationError("Mobile verification does not match this booking.")
    queryset = BookingPhoneVerification.objects.select_for_update() if lock else BookingPhoneVerification.objects
    verification = queryset.filter(
        id=payload.get("verification_id"),
        organization=organization,
        mobile_number=mobile_number,
        verified_at__isnull=False,
        consumed_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).first()
    if not verification:
        raise ValidationError("Please verify your mobile number again.")
    return verification
