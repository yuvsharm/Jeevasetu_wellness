import re

from django.core.exceptions import ValidationError

MOBILE_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


class JeevaSetuPasswordComplexityValidator:
    def validate(self, password, user=None):
        del user
        missing = []
        if re.search(r"[A-Z]", password) is None:
            missing.append("an uppercase letter")
        if re.search(r"[a-z]", password) is None:
            missing.append("a lowercase letter")
        if re.search(r"\d", password) is None:
            missing.append("a number")
        if re.search(r"[^A-Za-z0-9]", password) is None:
            missing.append("a special character")
        if missing:
            raise ValidationError(f"Password must include {', '.join(missing)}.", code="password_missing_complexity")

    def get_help_text(self):
        return "Your password must include uppercase and lowercase letters, a number, and a special character."


def normalize_email_address(value):
    return value.strip().lower() if value else ""


def normalize_mobile_number(value):
    normalized = re.sub(r"[\s().-]", "", value.strip())
    if normalized.startswith("00"):
        normalized = f"+{normalized[2:]}"
    if MOBILE_PATTERN.fullmatch(normalized) is None:
        raise ValidationError("Enter a valid E.164 mobile number, including country code.")
    return normalized
