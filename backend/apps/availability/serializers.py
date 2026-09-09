from datetime import datetime, time, timedelta
from apps.availability.services import _zone

from rest_framework import serializers

from apps.availability.models import (
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)
from apps.staff.models import StaffProfile


class OperatingDaySerializer(serializers.Serializer):
    weekday = serializers.IntegerField(min_value=0, max_value=6)
    is_open = serializers.BooleanField()
    opens_at = serializers.TimeField(required=False, allow_null=True)
    closes_at = serializers.TimeField(required=False, allow_null=True)

    def validate(self, attrs):
        if attrs["is_open"]:
            if not attrs.get("opens_at") or not attrs.get("closes_at"):
                raise serializers.ValidationError("Open days require opening and closing times.")
            if attrs["opens_at"] >= attrs["closes_at"]:
                raise serializers.ValidationError("Opening time must precede closing time.")
        return attrs


class OperatingHoursWriteSerializer(serializers.Serializer):
    days = OperatingDaySerializer(many=True)
    minimum_advance_notice_hours = serializers.IntegerField(min_value=1, max_value=168)

    def validate_days(self, value):
        weekdays = [item["weekday"] for item in value]
        if sorted(weekdays) != list(range(7)):
            raise serializers.ValidationError("Provide each weekday exactly once.")
        if not any(item["is_open"] for item in value):
            raise serializers.ValidationError("At least one operating day must be open.")
        return value


class CustomerSlotQuerySerializer(serializers.Serializer):
    therapy = serializers.UUIDField()
    requested_therapies = serializers.CharField(required=False, allow_blank=True)
    package = serializers.UUIDField(required=False)
    offer = serializers.UUIDField(required=False)
    family_member = serializers.UUIDField(required=False)
    date = serializers.DateField()


class RuleSerializer(serializers.ModelSerializer):
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True
    )

    class Meta:
        model = AvailabilityRule
        fields = (
            "id",
            "physiotherapist",
            "physiotherapist_name",
            "clinic",
            "weekday",
            "starts_at",
            "ends_at",
            "effective_from",
            "effective_until",
            "approval_status",
            "is_active",
            "review_reason",
            "created_at",
        )
        read_only_fields = (
            "id",
            "approval_status",
            "is_active",
            "review_reason",
            "created_at",
        )


class ExceptionSerializer(serializers.ModelSerializer):
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True
    )

    from_date = serializers.DateField(write_only=True, required=False)
    to_date = serializers.DateField(write_only=True, required=False)
    starts_at = serializers.DateTimeField(required=False)
    ends_at = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        start = attrs.pop("from_date", None)
        end = attrs.pop("to_date", None)
        if start is not None or end is not None:
            if start is None or end is None or end < start:
                raise serializers.ValidationError("Select a valid From Date and To Date.")
            if "starts_at" in attrs or "ends_at" in attrs:
                raise serializers.ValidationError("Use dates or times, not both.")
            if attrs.get("kind", getattr(self.instance, "kind", None)) != "UNAVAILABLE":
                raise serializers.ValidationError("Date ranges are only supported for leave.")
            clinic = attrs.get("clinic", getattr(self.instance, "clinic", None)) or self.context.get("clinic")
            if clinic is None:
                raise serializers.ValidationError("Select a clinic for date-only leave.")
            zone = _zone(clinic)
            attrs["starts_at"] = datetime.combine(start, time.min, zone)
            attrs["ends_at"] = datetime.combine(end + timedelta(days=1), time.min, zone)
        if self.instance is None and not all(attrs.get(key) for key in ("starts_at", "ends_at")):
            raise serializers.ValidationError("Select the leave date range.")
        return attrs

    class Meta:
        model = AvailabilityException
        fields = (
            "id",
            "physiotherapist",
            "physiotherapist_name",
            "clinic",
            "kind",
            "from_date",
            "to_date",
            "starts_at",
            "ends_at",
            "reason",
            "approval_status",
            "is_active",
            "review_reason",
            "created_at",
        )
        read_only_fields = (
            "id",
            "approval_status",
            "is_active",
            "review_reason",
            "created_at",
        )


class SelfRuleSerializer(RuleSerializer):
    class Meta(RuleSerializer.Meta):
        read_only_fields = RuleSerializer.Meta.read_only_fields + ("physiotherapist", "clinic")


class SelfExceptionSerializer(ExceptionSerializer):
    class Meta(ExceptionSerializer.Meta):
        read_only_fields = ExceptionSerializer.Meta.read_only_fields + (
            "physiotherapist",
            "clinic",
        )


class ReviewSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DeactivateSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class SlotQuerySerializer(serializers.Serializer):
    clinic = serializers.UUIDField()
    therapy = serializers.UUIDField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    physiotherapist = serializers.UUIDField(required=False)

    def validate(self, attrs):
        if (
            attrs["date_to"] < attrs["date_from"]
            or (attrs["date_to"] - attrs["date_from"]).days > 14
        ):
            raise serializers.ValidationError("Slot discovery supports a maximum 14-day range.")
        return attrs


class AuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True)
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True
    )

    class Meta:
        model = AvailabilityAuditEvent
        fields = (
            "id",
            "actor_name",
            "physiotherapist_name",
            "action",
            "reason",
            "rejection_code",
            "created_at",
        )


def validate_profile(value, organization, clinic):
    if (
        not isinstance(value, StaffProfile)
        or value.organization_id != organization.id
        or value.clinic_id != clinic.id
        or value.staff_type != "PHYSIOTHERAPIST"
    ):
        raise serializers.ValidationError("The Physiotherapist is unavailable.")
