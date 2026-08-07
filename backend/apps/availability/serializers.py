from rest_framework import serializers

from apps.availability.models import (
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)
from apps.staff.models import StaffProfile


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

    class Meta:
        model = AvailabilityException
        fields = (
            "id",
            "physiotherapist",
            "physiotherapist_name",
            "clinic",
            "kind",
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
