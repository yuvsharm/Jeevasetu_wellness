import re

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from apps.accounts.models import Role
from apps.accounts.role_policy import actor_role_scope
from apps.patients.models import CaregiverRelationship, CustomerFamilyMember, PatientAddress, PatientProfile


class CustomerFamilyMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerFamilyMember
        fields = ("id", "full_name", "age", "gender", "relationship", "relevant_details", "created_at")
        read_only_fields = ("id", "created_at")


def normalize_mobile(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise serializers.ValidationError("Enter a valid Indian mobile number.")
    return digits


class PatientAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientAddress
        fields = (
            "id",
            "label",
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "is_primary",
            "is_active",
        )
        read_only_fields = ("id",)


class CaregiverRelationshipSerializer(serializers.ModelSerializer):
    class Meta:
        model = CaregiverRelationship
        fields = ("id", "full_name", "relationship", "mobile_number", "is_active")
        read_only_fields = ("id",)


class PatientListSerializer(serializers.ModelSerializer):
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    mobile_hint = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        fields = (
            "id",
            "patient_identifier",
            "full_name",
            "mobile_hint",
            "gender",
            "date_of_birth",
            "age",
            "clinic",
            "clinic_name",
            "is_active",
        )

    def get_mobile_hint(self, value) -> str:
        return f"******{value.mobile_number[-4:]}"


class PatientProfileSerializer(serializers.ModelSerializer):
    mobile_number = serializers.CharField(max_length=20)
    emergency_contact_mobile = serializers.CharField(max_length=20)
    guardian_mobile = serializers.CharField(max_length=20, required=False, allow_blank=True)
    addresses = PatientAddressSerializer(many=True)
    caregivers = CaregiverRelationshipSerializer(many=True, required=False)
    profile_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = PatientProfile
        fields = (
            "id",
            "patient_identifier",
            "full_name",
            "mobile_number",
            "email",
            "gender",
            "date_of_birth",
            "age",
            "clinic",
            "profile_photo",
            "profile_photo_url",
            "emergency_contact_name",
            "emergency_contact_relationship",
            "emergency_contact_mobile",
            "guardian_name",
            "guardian_relationship",
            "guardian_mobile",
            "is_active",
            "addresses",
            "caregivers",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "patient_identifier",
            "profile_photo_url",
            "is_active",
            "created_at",
            "updated_at",
        )
        extra_kwargs = {"profile_photo": {"write_only": True, "required": False}}

    def get_profile_photo_url(self, value) -> str | None:
        if not value.profile_photo:
            return None
        request = self.context.get("request")
        path = f"/api/v1/patients/{value.pk}/photo/"
        return request.build_absolute_uri(path) if request else path

    def validate_mobile_number(self, value):
        return normalize_mobile(value)

    def validate_emergency_contact_mobile(self, value):
        return normalize_mobile(value)

    def validate_guardian_mobile(self, value):
        return normalize_mobile(value) if value else ""

    def validate_profile_photo(self, value):
        if value.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise serializers.ValidationError("Upload a JPG, PNG, or WebP photograph.")
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Profile photographs must not exceed 2 MB.")
        return value

    def validate(self, attrs):
        request = self.context["request"]
        organization = request.organization
        clinic = attrs.get("clinic", getattr(self.instance, "clinic", None))
        if clinic is None or clinic.organization_id != organization.id or not clinic.is_active:
            raise serializers.ValidationError({"clinic": "The selected clinic is unavailable."})
        self_access = self.instance and self.instance.user_id == request.user.id
        if self_access:
            if "clinic" in attrs and clinic != self.instance.clinic:
                raise serializers.ValidationError(
                    {"clinic": "Clinic assignment cannot be changed."}
                )
        else:
            level, clinic_ids = actor_role_scope(request.user, organization)
            if level == Role.MANAGER and (clinic_ids is None or clinic.id not in clinic_ids):
                raise serializers.ValidationError({"clinic": "The selected clinic is unavailable."})
            if self.instance and clinic != self.instance.clinic and level != Role.OWNER:
                raise serializers.ValidationError(
                    {"clinic": "Only an Owner may transfer a patient."}
                )
        addresses = attrs.get("addresses")
        if self.instance is None and not addresses:
            raise serializers.ValidationError({"addresses": "A primary address is required."})
        if addresses is not None:
            active = [address for address in addresses if address.get("is_active", True)]
            if len(active) > 4 or sum(address.get("is_primary", False) for address in active) != 1:
                raise serializers.ValidationError(
                    {
                        "addresses": (
                            "Provide one primary and no more than three additional addresses."
                        )
                    }
                )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        addresses = validated_data.pop("addresses")
        caregivers = validated_data.pop("caregivers", [])
        try:
            patient = PatientProfile(
                organization=self.context["request"].organization, **validated_data
            )
            patient.save()
            for address in addresses:
                value = PatientAddress(patient=patient, **address)
                value.full_clean()
                value.save()
            for caregiver in caregivers:
                value = CaregiverRelationship(patient=patient, **caregiver)
                value.full_clean()
                value.save()
            return patient
        except (IntegrityError, DjangoValidationError) as error:
            raise serializers.ValidationError(
                "The patient details conflict with an existing active record or are invalid."
            ) from error

    @transaction.atomic
    def update(self, instance, validated_data):
        addresses = validated_data.pop("addresses", None)
        caregivers = validated_data.pop("caregivers", None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        try:
            instance.save()
            if addresses is not None:
                instance.addresses.update(is_active=False, is_primary=False)
                for address in addresses:
                    value = PatientAddress(patient=instance, **address)
                    value.full_clean()
                    value.save()
            if caregivers is not None:
                instance.caregivers.update(is_active=False)
                for caregiver in caregivers:
                    value = CaregiverRelationship(patient=instance, **caregiver)
                    value.full_clean()
                    value.save()
            return instance
        except (IntegrityError, DjangoValidationError) as error:
            raise serializers.ValidationError(
                "The patient details conflict with an existing active record or are invalid."
            ) from error


class PatientStatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField()
    reason = serializers.CharField(max_length=255)


class CustomerSelfProfileSerializer(serializers.Serializer):
    def to_representation(self, value):
        from datetime import date

        primary = value.addresses.filter(is_active=True, is_primary=True).first()
        age = value.age
        if value.date_of_birth:
            today = date.today()
            born = value.date_of_birth
            age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
        return {
            "id": str(value.pk),
            "first_name": value.user.first_name,
            "last_name": value.user.last_name,
            "full_name": value.full_name,
            "email": value.email or value.user.email,
            "mobile_number": value.user.mobile_number,
            "gender": value.gender,
            "date_of_birth": value.date_of_birth,
            "age": age,
            "photo_url": "/api/customer/profile/photo" if value.profile_photo else "",
            "address": PatientAddressSerializer(primary).data if primary else None,
            "updated_at": value.updated_at,
        }


class CustomerSelfProfileUpdateSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=150, required=False)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    gender = serializers.ChoiceField(choices=PatientProfile.Gender.choices, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    address_line_1 = serializers.CharField(max_length=255, required=False)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    landmark = serializers.CharField(max_length=160, required=False, allow_blank=True)
    city = serializers.CharField(max_length=120, required=False)
    region = serializers.CharField(max_length=120, required=False)
    pin_code = serializers.RegexField(r"^[1-9]\d{5}$", required=False)

    def validate_date_of_birth(self, value):
        from datetime import date

        if value and value > date.today():
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        return value


class CustomerPhotoSerializer(serializers.Serializer):
    profile_photo = serializers.ImageField()

    def validate_profile_photo(self, value):
        if value.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise serializers.ValidationError("Upload a JPG, PNG, or WebP photograph.")
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Profile photographs must not exceed 2 MB.")
        return value


class CustomerMobileChangeSerializer(serializers.Serializer):
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    booking_verification_token = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value):
        if not self.context["request"].user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value
