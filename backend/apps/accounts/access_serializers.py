from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent, User
from apps.accounts.role_policy import assign_role, record_role_event, update_role_scope
from apps.tenancy.models import Clinic


class AccessClinicSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(read_only=True)


class AccessRoleSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id", read_only=True)
    organization_id = serializers.UUIDField(source="organization.id", read_only=True)
    clinic_id = serializers.UUIDField(source="clinic.id", read_only=True, allow_null=True)
    scope = serializers.SerializerMethodField()

    class Meta:
        model = RoleAssignment
        fields = (
            "id",
            "user_id",
            "organization_id",
            "clinic_id",
            "role",
            "scope",
            "is_active",
            "created_at",
            "updated_at",
            "disabled_at",
            "disabled_reason",
        )
        read_only_fields = fields

    def get_scope(self, value) -> str:
        return "clinic" if value.clinic_id else "organization"


class AccessOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    slug = serializers.CharField(read_only=True)


class AccessSummarySerializer(serializers.Serializer):
    user_id = serializers.UUIDField(read_only=True)
    organization = AccessOrganizationSerializer(read_only=True)
    permitted_clinics = AccessClinicSerializer(many=True, read_only=True)
    roles = AccessRoleSerializer(many=True, read_only=True)


class RoleCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField(write_only=True)
    role = serializers.CharField(max_length=32)
    clinic_id = serializers.UUIDField(write_only=True, required=False, allow_null=True)

    def validate(self, attrs):
        organization = self.context["organization"]
        target = User.objects.filter(pk=attrs["user_id"]).first()
        if target is None:
            raise serializers.ValidationError({"user_id": "The selected identity is unavailable."})
        if attrs["role"] not in Role.values:
            record_role_event(
                RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
                actor=self.context["request"].user,
                target=target,
                organization=organization,
                new_role=attrs["role"],
                request_id=self.context.get("request_id", ""),
            )
            raise serializers.ValidationError({"role": "Unsupported role."})
        clinic = None
        if attrs.get("clinic_id"):
            clinic = Clinic.objects.filter(
                pk=attrs["clinic_id"], organization=organization, is_active=True
            ).first()
            if clinic is None:
                raise serializers.ValidationError(
                    {"clinic_id": "The selected clinic is unavailable."}
                )
        attrs["target"] = target
        attrs["clinic"] = clinic
        return attrs

    def create(self, validated_data):
        try:
            return assign_role(
                actor=self.context["request"].user,
                target=validated_data["target"],
                organization=self.context["organization"],
                role=validated_data["role"],
                clinic=validated_data["clinic"],
                request_id=self.context.get("request_id", ""),
            )
        except DjangoValidationError as error:
            detail = error.message_dict if hasattr(error, "message_dict") else error.messages
            raise serializers.ValidationError(detail) from error


class RoleUpdateSerializer(serializers.Serializer):
    clinic_id = serializers.UUIDField(required=True, allow_null=True)

    def validate(self, attrs):
        unsupported = set(self.initial_data) - {"clinic_id"}
        if unsupported:
            raise serializers.ValidationError("Only clinic_id may be updated.")
        if "clinic_id" not in self.initial_data:
            raise serializers.ValidationError({"clinic_id": "This field is required."})
        organization = self.context["organization"]
        clinic = None
        if attrs["clinic_id"]:
            clinic = Clinic.objects.filter(
                pk=attrs["clinic_id"], organization=organization, is_active=True
            ).first()
            if clinic is None:
                raise serializers.ValidationError(
                    {"clinic_id": "The selected clinic is unavailable."}
                )
        attrs["clinic"] = clinic
        return attrs

    def update(self, instance, validated_data):
        try:
            return update_role_scope(
                instance,
                actor=self.context["request"].user,
                clinic=validated_data["clinic"],
                request_id=self.context.get("request_id", ""),
            )
        except DjangoValidationError as error:
            detail = error.message_dict if hasattr(error, "message_dict") else error.messages
            raise serializers.ValidationError(detail) from error


class RoleActionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, trim_whitespace=True, required=False)


class RoleDeactivateSerializer(RoleActionSerializer):
    reason = serializers.CharField(max_length=255, trim_whitespace=True, required=True)
