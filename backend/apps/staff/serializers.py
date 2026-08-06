from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.accounts.models import Role, User
from apps.accounts.role_policy import assign_role
from apps.staff.models import ServiceArea, Specialization, StaffDocument, StaffProfile
from apps.tenancy.models import ClinicMembership, OrganizationMembership


class SpecializationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = ("id", "name")


class ServiceAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceArea
        fields = ("id", "name", "pin_codes")


class StaffDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StaffDocument
        fields = ("id", "label", "file", "created_at")
        read_only_fields = ("id", "created_at")


class StaffStatusActionSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
    reason = serializers.CharField(max_length=255, required=False)


class StaffDetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class StaffOptionsSerializer(serializers.Serializer):
    specializations = SpecializationSerializer(many=True, read_only=True)
    service_areas = ServiceAreaSerializer(many=True, read_only=True)


class StaffProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(source="user.get_full_name", read_only=True)
    email = serializers.EmailField(source="user.email")
    mobile = serializers.CharField(source="user.mobile_number")
    is_active = serializers.SerializerMethodField()
    specialization_ids = serializers.PrimaryKeyRelatedField(
        source="specializations",
        queryset=Specialization.objects.filter(is_active=True),
        many=True,
        required=False,
    )
    service_area_ids = serializers.PrimaryKeyRelatedField(
        source="service_areas",
        queryset=ServiceArea.objects.filter(is_active=True),
        many=True,
        required=False,
    )
    documents = StaffDocumentSerializer(many=True, read_only=True)

    class Meta:
        model = StaffProfile
        fields = (
            "id",
            "user_id",
            "staff_type",
            "full_name",
            "email",
            "mobile",
            "profile_photo",
            "gender",
            "date_of_birth",
            "qualification",
            "registration_number",
            "experience_years",
            "specialization_ids",
            "languages_known",
            "alternate_mobile",
            "emergency_contact",
            "current_address",
            "city",
            "pin_code",
            "clinic",
            "service_area_ids",
            "availability",
            "is_online",
            "joining_date",
            "is_active",
            "bio",
            "documents",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "user_id", "staff_type", "is_active", "created_at", "updated_at")

    def get_is_active(self, value) -> bool:
        return value.user.role_assignments.filter(
            organization=value.organization, role=value.staff_type, is_active=True
        ).exists()

    def validate(self, attrs):
        request = self.context["request"]
        organization = request.organization
        clinic = attrs.get("clinic", getattr(self.instance, "clinic", None))
        if clinic and (clinic.organization_id != organization.id or not clinic.is_active):
            raise serializers.ValidationError({"clinic": "The selected clinic is unavailable."})
        if self.instance and "clinic" in attrs and clinic != self.instance.clinic:
            raise serializers.ValidationError(
                {"clinic": "Clinic reassignment must use the access-management workflow."}
            )
        for area in attrs.get("service_areas", []):
            if area.organization_id != organization.id:
                raise serializers.ValidationError(
                    {"service_area_ids": "A service area is outside this organization."}
                )
        return attrs

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        specializations = validated_data.pop("specializations", None)
        service_areas = validated_data.pop("service_areas", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        if user_data:
            instance.user.email = user_data.get("email", instance.user.email)
            instance.user.mobile_number = user_data.get(
                "mobile_number", instance.user.mobile_number
            )
            instance.user.full_clean()
            instance.user.save(update_fields=("email", "mobile_number"))
        instance.full_clean()
        instance.save()
        if specializations is not None:
            instance.specializations.set(specializations)
        if service_areas is not None:
            instance.service_areas.set(service_areas)
        return instance


class StaffCreateSerializer(StaffProfileSerializer):
    full_name = serializers.CharField(write_only=True, max_length=255)
    email = serializers.EmailField(write_only=True)
    mobile = serializers.RegexField(r"^\+[1-9]\d{7,14}$", write_only=True)
    staff_type = serializers.ChoiceField(choices=(Role.MANAGER, Role.PHYSIOTHERAPIST))

    class Meta(StaffProfileSerializer.Meta):
        read_only_fields = ("id", "user_id", "is_active", "created_at", "updated_at")

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        organization = request.organization
        full_name = validated_data.pop("full_name").strip().split(maxsplit=1)
        email = validated_data.pop("email")
        mobile = validated_data.pop("mobile")
        role = validated_data["staff_type"]
        clinic = validated_data.get("clinic")
        if role == Role.PHYSIOTHERAPIST and clinic is None:
            raise serializers.ValidationError({"clinic": "Physiotherapists require a clinic."})
        try:
            user = User(
                username=email,
                email=email,
                mobile_number=mobile,
                first_name=full_name[0],
                last_name=full_name[1] if len(full_name) > 1 else "",
            )
            user.set_unusable_password()
            user.full_clean()
            user.save()
            membership = OrganizationMembership.objects.create(user=user, organization=organization)
            if clinic:
                ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)
            assign_role(
                actor=request.user, target=user, organization=organization, role=role, clinic=clinic
            )
            specializations = validated_data.pop("specializations", [])
            service_areas = validated_data.pop("service_areas", [])
            profile = StaffProfile.objects.create(
                user=user, organization=organization, **validated_data
            )
            profile.specializations.set(specializations)
            profile.service_areas.set(service_areas)
            return profile
        except (IntegrityError, DjangoValidationError) as error:
            raise serializers.ValidationError(
                "Email or mobile already exists, or the staff profile is invalid."
            ) from error
