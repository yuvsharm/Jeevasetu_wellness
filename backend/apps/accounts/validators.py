import re

from django.core.exceptions import ValidationError

MOBILE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def normalize_email_address(value):
    return value.strip().lower() if value else ""


def normalize_mobile_number(value):
    normalized = re.sub(r"[\s().-]", "", value.strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if MOBILE_PATTERN.fullmatch(normalized) is None:
        raise ValidationError("Enter a valid E.164 mobile number, including country code.")
    return normalized
