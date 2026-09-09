"""Therapist identity dates: age is derived, never persisted."""
from zoneinfo import ZoneInfo
from django.utils import timezone
from rest_framework import serializers


def identity_today(value=None, organization=None):
    clinic = getattr(value, "clinic", None)
    organization = organization or getattr(value, "organization", None)
    zone = (getattr(clinic, "timezone", None) or getattr(organization, "timezone", None) or "Asia/Kolkata")
    return timezone.now().astimezone(ZoneInfo(zone)).date()


def age_on(dob, today):
    if dob is None:
        return None
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def validate_dob(dob, today=None):
    if dob is None:
        raise serializers.ValidationError("Date of birth is required.")
    today = today or identity_today()
    if dob > today:
        raise serializers.ValidationError("Date of birth cannot be in the future.")
    age = age_on(dob, today)
    if age < 18:
        raise serializers.ValidationError("Therapist must be at least 18 years old.")
    if age > 80:
        raise serializers.ValidationError("Therapist must be no older than 80 years.")
    return dob


def canonical_dob(value):
    # Application DOB is an immutable enrollment snapshot after approval.
    approved = getattr(value, "approved_profile", None)
    staff = getattr(approved, "staff_profile", None) if approved else getattr(value, "staff_profile", None)
    return staff.date_of_birth if staff else getattr(value, "date_of_birth", None)


def derived_age(value):
    return age_on(canonical_dob(value), identity_today(value))


class DobSerializer(serializers.Serializer):
    date_of_birth = serializers.DateField(error_messages={"invalid": "Enter a valid date of birth.", "required": "Date of birth is required."})

    def validate_date_of_birth(self, value):
        return validate_dob(value, identity_today(organization=self.context.get("organization")))
