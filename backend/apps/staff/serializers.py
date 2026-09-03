from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Role, User
from apps.accounts.role_policy import assign_role
from apps.appointments.models import TherapyOption
from apps.staff.models import ServiceArea, Specialization, StaffDocument, StaffProfile
from apps.tenancy.models import ClinicMembership, OrganizationMembership
from apps.appointments.booking_verification import resolve_booking_verification
from apps.practitioners.serializers import DocumentUploadSerializer


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
    clinic_name = serializers.CharField(source="clinic.name", read_only=True, allow_null=True)
    specialization_names = serializers.SlugRelatedField(
        source="specializations", slug_field="name", many=True, read_only=True
    )
    verified_therapy_ids = serializers.SerializerMethodField()
    verified_therapy_names = serializers.SerializerMethodField()
    therapy_competency_ids = serializers.PrimaryKeyRelatedField(
        source="therapy_competencies",
        queryset=TherapyOption.objects.all(),
        many=True,
        required=False,
    )
    profile_source = serializers.SerializerMethodField()
    approved_weekly_rule_count = serializers.IntegerField(read_only=True, default=0)
    approval_status = serializers.SerializerMethodField()
    activation_status = serializers.SerializerMethodField()
    is_publicly_visible = serializers.BooleanField(
        source="practitioner_profile.is_publicly_visible", required=False
    )
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
            "experience_months",
            "specialization_ids",
            "languages_known",
            "alternate_mobile",
            "emergency_contact",
            "current_address",
            "city",
            "pin_code",
            "clinic",
            "clinic_name",
            "specialization_names",
            "verified_therapy_ids",
            "verified_therapy_names",
            "therapy_competency_ids",
            "profile_source",
            "approved_weekly_rule_count",
            "approval_status",
            "activation_status",
            "is_publicly_visible",
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

    def get_verified_therapy_ids(self, value) -> list[str]:
        return [str(item.id) for item in value.therapy_competencies.filter(is_active=True)]

    def get_verified_therapy_names(self, value) -> list[str]:
        return list(
            value.therapy_competencies.filter(is_active=True).values_list("name", flat=True)
        )

    def get_profile_source(self, value) -> str:
        try:
            value.practitioner_profile.source_application
        except (AttributeError, ObjectDoesNotExist):
            return "STAFF_CREATED"
        return "PRACTITIONER_APPLICATION"

    def get_approval_status(self, value) -> str:
        try:
            application = value.practitioner_profile.source_application
        except (AttributeError, ObjectDoesNotExist):
            application = None
        if application is not None and application.status in ("PENDING", "REJECTED"):
            return "PENDING_APPLICATION" if application.status == "PENDING" else "REJECTED"
        try:
            return "VERIFIED_APPROVED" if value.practitioner_profile.is_approved else "PENDING_APPLICATION"
        except (AttributeError, ObjectDoesNotExist):
            return "NOT_APPLICABLE"

    def get_activation_status(self, value) -> str:
        return "ACCOUNT_ACTIVATED" if value.user.has_usable_password() else "ACTIVATION_PENDING"

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
        for therapy in attrs.get("therapy_competencies", []):
            if therapy.organization_id != organization.id or not therapy.is_active:
                raise serializers.ValidationError(
                    {"therapy_competency_ids": "Select active therapies from this organization."}
                )
        return attrs

    def update(self, instance, validated_data):
        user_data = validated_data.pop("user", {})
        practitioner_data = validated_data.pop("practitioner_profile", {})
        specializations = validated_data.pop("specializations", None)
        service_areas = validated_data.pop("service_areas", None)
        therapy_competencies = validated_data.pop("therapy_competencies", None)
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
        if therapy_competencies is not None:
            instance.therapy_competencies.set(therapy_competencies)
        if practitioner_data and hasattr(instance, "practitioner_profile"):
            instance.practitioner_profile.is_publicly_visible = practitioner_data["is_publicly_visible"]
            instance.practitioner_profile.save(update_fields=("is_publicly_visible", "updated_at"))
        return instance


class StaffCreateSerializer(StaffProfileSerializer):
    full_name = serializers.CharField(write_only=True, max_length=255)
    email = serializers.EmailField(write_only=True)
    mobile = serializers.RegexField(
        r"^\+91[6-9]\d{9}$",
        write_only=True,
        error_messages={"invalid": "Enter mobile number in +91XXXXXXXXXX format."},
    )
    staff_type = serializers.ChoiceField(choices=(Role.MANAGER, Role.PHYSIOTHERAPIST))
    mobile_verification_token = serializers.CharField(write_only=True, required=False)
    password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, required=False, trim_whitespace=False)
    government_id_document = serializers.FileField(write_only=True, required=False)
    qualification_document = serializers.FileField(write_only=True, required=False)
    experience_document = serializers.FileField(write_only=True, required=False)
    registration_document = serializers.FileField(write_only=True, required=False)
    other_document = serializers.FileField(write_only=True, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    emergency_contact = serializers.CharField(required=False, allow_blank=True)
    current_address = serializers.CharField(required=False, allow_blank=True)
    city = serializers.CharField(required=False, allow_blank=True)
    pin_code = serializers.CharField(required=False, allow_blank=True)
    practitioner_type = serializers.ChoiceField(
        choices=("PHYSIOTHERAPIST", "WELLNESS"), required=False, write_only=True
    )
    operationally_active = serializers.BooleanField(required=False, default=True, write_only=True)

    class Meta(StaffProfileSerializer.Meta):
        fields = StaffProfileSerializer.Meta.fields + (
            "mobile_verification_token", "password", "confirm_password",
            "government_id_document", "qualification_document", "experience_document",
            "registration_document", "other_document",
            "practitioner_type", "operationally_active",
        )
        read_only_fields = ("id", "user_id", "is_active", "created_at", "updated_at")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("experience_years", 0) > 60:
            raise serializers.ValidationError({"experience_years": "Experience cannot exceed 60 years."})
        password = attrs.get("password")
        if bool(password) != bool(attrs.get("mobile_verification_token")):
            raise serializers.ValidationError(
                {"mobile_verification_token": "Verify the mobile number before creating credentials."}
            )
        if password:
            if password != attrs.pop("confirm_password", None):
                raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
            from django.contrib.auth import password_validation

            password_validation.validate_password(password)
            if not (
                any(char.isupper() for char in password)
                and any(char.islower() for char in password)
                and any(char.isdigit() for char in password)
                and any(not char.isalnum() for char in password)
            ):
                raise serializers.ValidationError({
                    "password": "Password requires uppercase, lowercase, number and special character."
                })
        for field in (
            "government_id_document", "qualification_document", "experience_document",
            "registration_document", "other_document",
        ):
            if attrs.get(field):
                DocumentUploadSerializer().validate_file(attrs[field])
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        organization = request.organization
        full_name = validated_data.pop("full_name").strip().split(maxsplit=1)
        email = validated_data.pop("email")
        mobile = validated_data.pop("mobile")
        role = validated_data["staff_type"]
        practitioner_type = validated_data.pop("practitioner_type", "PHYSIOTHERAPIST")
        operationally_active = validated_data.pop("operationally_active", True)
        verification_token = validated_data.pop("mobile_verification_token", None)
        password = validated_data.pop("password", None)
        validated_data.pop("confirm_password", None)
        documents = {
            "Government identity proof": validated_data.pop("government_id_document", None),
            "Qualification certificate": validated_data.pop("qualification_document", None),
            "Experience certificate": validated_data.pop("experience_document", None),
            "Registration / licence": validated_data.pop("registration_document", None),
            "Other verification document": validated_data.pop("other_document", None),
        }
        practitioner_data = validated_data.pop("practitioner_profile", {})
        clinic = validated_data.get("clinic")
        validated_data.setdefault("date_of_birth", None)
        validated_data.setdefault("emergency_contact", "")
        validated_data.setdefault("current_address", "")
        validated_data.setdefault("city", "")
        validated_data.setdefault("pin_code", "")
        if role == Role.PHYSIOTHERAPIST and clinic is None:
            raise serializers.ValidationError({"clinic": "Physiotherapists require a clinic."})
        if role == Role.PHYSIOTHERAPIST and not validated_data.get("service_areas"):
            raise serializers.ValidationError({"service_area_ids": "Select at least one service area."})
        if role == Role.PHYSIOTHERAPIST and not validated_data.get("therapy_competencies"):
            raise serializers.ValidationError({"therapy_competency_ids": "Select at least one therapy competency."})
        if role == Role.PHYSIOTHERAPIST and verification_token:
            if not documents["Government identity proof"]:
                raise serializers.ValidationError({"government_id_document": "Government identity proof is required."})
            if not documents["Qualification certificate"]:
                raise serializers.ValidationError({"qualification_document": "Qualification certificate is required."})
            if validated_data.get("registration_number") and not documents["Registration / licence"]:
                raise serializers.ValidationError({"registration_document": "Registration / licence document is required."})
        verification = None
        if verification_token:
            try:
                verification = resolve_booking_verification(
                    organization=organization,
                    mobile_number=mobile[-10:],
                    token=verification_token,
                    lock=True,
                )
            except Exception as error:
                raise serializers.ValidationError(
                    {"mobile": getattr(error, "messages", [str(error)])}
                ) from error
        try:
            user = User(
                username=email,
                email=email,
                mobile_number=mobile,
                first_name=full_name[0],
                last_name=full_name[1] if len(full_name) > 1 else "",
            )
            user.set_password(password) if password else user.set_unusable_password()
            user.full_clean()
            user.save()
            membership = OrganizationMembership.objects.create(user=user, organization=organization)
            if clinic:
                ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)
            assignment = assign_role(
                actor=request.user, target=user, organization=organization, role=role, clinic=clinic
            )
            if not operationally_active:
                from apps.accounts.role_policy import disable_role

                disable_role(assignment, actor=request.user, reason="Created inactive by Owner.")
            specializations = validated_data.pop("specializations", [])
            service_areas = validated_data.pop("service_areas", [])
            therapy_competencies = validated_data.pop("therapy_competencies", [])
            profile = StaffProfile.objects.create(
                user=user, organization=organization, **validated_data
            )
            profile.specializations.set(specializations)
            profile.service_areas.set(service_areas)
            profile.therapy_competencies.set(therapy_competencies)
            for label, file in documents.items():
                if file:
                    StaffDocument.objects.create(profile=profile, label=label, file=file)
            if role == Role.PHYSIOTHERAPIST:
                from apps.practitioners.models import PractitionerApplication, PractitionerProfile

                PractitionerProfile.objects.create(
                    user=user,
                    organization=organization,
                    clinic=clinic,
                    staff_profile=profile,
                    category=practitioner_type,
                    qualification_specialization=profile.qualification,
                    is_approved=True,
                    is_publicly_visible=practitioner_data.get("is_publicly_visible", False),
                    is_open_to_work=True,
                    approved_at=timezone.now(),
                )
            if verification:
                verification.consumed_at = timezone.now()
                verification.save(update_fields=("consumed_at",))
            return profile
        except (IntegrityError, DjangoValidationError) as error:
            if User.objects.filter(mobile_number=mobile).exists():
                raise serializers.ValidationError({
                    "mobile": "This mobile number is already registered with JeevaSetu."
                }) from error
            raise serializers.ValidationError("Email already exists, or the staff profile is invalid.") from error
