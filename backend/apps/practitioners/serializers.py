from pathlib import Path

from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.practitioners.models import (
    PractitionerApplication,
    PractitionerCompetency,
    PractitionerDocument,
    PractitionerProfile,
)
from apps.practitioners.services import upload_checksum
from apps.practitioners.dob import canonical_dob, derived_age, identity_today, validate_dob

ALLOWED_UPLOADS = {
    "application/pdf": {".pdf"},
}
MAX_UPLOAD_BYTES = 25 * 1024 * 1024


class CompetencySerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)

    class Meta:
        model = PractitionerCompetency
        fields = ("id", "therapy", "therapy_name", "experience_months", "verification_status")
        read_only_fields = ("id", "therapy_name", "verification_status")

    def validate_therapy(self, value):
        if not value.is_active or value.organization_id != self.context["request"].organization.id:
            raise serializers.ValidationError("Select an approved NuriPain Ease service.")
        return value


class DocumentMetadataSerializer(serializers.ModelSerializer):
    class Meta:
        model = PractitionerDocument
        fields = (
            "id",
            "kind",
            "original_name",
            "content_type",
            "size_bytes",
            "verification_status",
            "created_at",
        )


class DocumentUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = PractitionerDocument
        fields = ("id", "kind", "file")
        read_only_fields = ("id",)

    def validate_file(self, value):
        suffix = Path(value.name).suffix.lower()
        content_type = getattr(value, "content_type", "")
        if value.size > MAX_UPLOAD_BYTES:
            raise serializers.ValidationError("Files must not exceed 25 MB.")
        if content_type not in ALLOWED_UPLOADS or suffix not in ALLOWED_UPLOADS[content_type]:
            raise serializers.ValidationError("Upload a PDF file.")
        header = value.read(8)
        value.seek(0)
        if not header.startswith(b"%PDF-"):
            raise serializers.ValidationError("The file content does not match an allowed format.")
        return value

    def create(self, validated_data):
        file = validated_data["file"]
        application = self.context["application"]
        kind = validated_data["kind"]
        with transaction.atomic():
            previous = application.documents.select_for_update().filter(kind=kind).first()
            previous_storage = previous.file.storage if previous else None
            previous_name = previous.file.name if previous else None
            if previous:
                previous.delete()
            document = PractitionerDocument.objects.create(
                application=application,
                kind=kind,
                file=file,
                original_name=Path(file.name).name[:255],
                content_type=file.content_type,
                size_bytes=file.size,
                checksum_sha256=upload_checksum(file),
            )
            if previous_storage and previous_name:
                transaction.on_commit(lambda: previous_storage.delete(previous_name))
            return document


class ProfilePhotoUploadSerializer(serializers.Serializer):
    profile_photo = serializers.ImageField()

    def validate_profile_photo(self, value):
        if value.size > 10 * 1024 * 1024:
            raise serializers.ValidationError("Profile photographs must not exceed 10 MB.")
        if getattr(value, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
            raise serializers.ValidationError("Upload a JPEG, PNG, or WebP photograph.")
        return value


class ApplicationSerializer(serializers.ModelSerializer):
    therapy_ids = serializers.ListField(child=serializers.UUIDField(), required=False, write_only=True)
    service_area_names = serializers.SlugRelatedField(source="service_areas", slug_field="name", many=True, read_only=True)
    age = serializers.SerializerMethodField()

    def get_age(self, value):
        return derived_age(value)

    def to_representation(self, instance):
        data = super().to_representation(instance)
        dob = canonical_dob(instance)
        data["date_of_birth"] = dob.isoformat() if dob else None
        return data

    competencies = CompetencySerializer(many=True, read_only=True)
    documents = DocumentMetadataSerializer(many=True, read_only=True)
    has_profile_photo = serializers.SerializerMethodField()

    class Meta:
        model = PractitionerApplication
        exclude = ("organization", "applicant", "internal_review_notes")
        read_only_fields = (
            "id",
            "status",
            "correction_reason",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "reviewed_by",
            "approved_profile",
            "created_at",
            "updated_at",
            "profile_photo",
        )

    def validate_date_of_birth(self, value):
        if value is None:  # Incomplete drafts may autosave; submission/approval require DOB.
            return None
        return validate_dob(value, identity_today(self.instance, self.context["request"].organization))

    def get_has_profile_photo(self, value) -> bool:
        return bool(value.profile_photo)

    def validate_passing_year(self, value):
        if value is None:
            return value
        if value > timezone.localdate().year:
            raise serializers.ValidationError("Passing year cannot be in the future.")
        return value

    def validate_languages(self, value):
        if (
            not isinstance(value, list)
            or len(value) > 20
            or any(not isinstance(item, str) or not item.strip() for item in value)
        ):
            raise serializers.ValidationError("Provide a list of languages.")
        return [item.strip()[:60] for item in value]

    def validate_last_completed_step(self, value):
        if value > 5:
            raise serializers.ValidationError("Application step must be between 0 and 5.")
        return value

    def validate(self, attrs):
        instance = self.instance
        if "therapy_ids" in attrs:
            from apps.appointments.models import TherapyOption
            ids = set(attrs["therapy_ids"])
            if not ids or TherapyOption.objects.filter(pk__in=ids, is_active=True, organization=self.context["request"].organization).count() != len(ids):
                raise serializers.ValidationError({"therapy_ids": "Select active therapy competencies."})
        if instance and instance.qualification_title and "mobile_number" in attrs and attrs["mobile_number"] != instance.applicant.mobile_number:
            raise serializers.ValidationError({"mobile_number": "Your verified account mobile cannot be changed through an application edit."})
        for area in attrs.get("service_areas", []):
            if area.organization_id != self.context["request"].organization.id or not area.is_active:
                raise serializers.ValidationError({"service_areas": "Select active service areas from this organization."})
        if "working_days" in attrs:
            days = attrs["working_days"]
            if not isinstance(days, list) or any(type(day) is not int or day not in range(7) for day in days):
                raise serializers.ValidationError({"working_days": "Select valid working days."})
        start = attrs.get("working_hours_start", getattr(instance, "working_hours_start", None))
        end = attrs.get("working_hours_end", getattr(instance, "working_hours_end", None))
        if start and end and start >= end:
            raise serializers.ValidationError({"working_hours_end": "Working hours must end after they start."})
        if instance and instance.status not in (
            PractitionerApplication.Status.DRAFT,
            PractitionerApplication.Status.CORRECTION_REQUIRED,
        ):
            raise serializers.ValidationError("This application is not editable.")
        clinic = attrs.get("clinic", getattr(instance, "clinic", None))
        if clinic and (
            clinic.organization_id != self.context["request"].organization.id
            or not clinic.is_active
        ):
            raise serializers.ValidationError(
                {"clinic": "Select an active clinic in this organization."}
            )
        return attrs

    def create(self, validated_data):
        validated_data.pop("therapy_ids", None)
        value = PractitionerApplication(
            applicant=self.context["request"].user,
            organization=self.context["request"].organization,
            **validated_data,
        )
        value.full_clean()
        value.save()
        return value

    def update(self, instance, validated_data):
        therapy_ids = validated_data.pop("therapy_ids", None)
        areas = validated_data.pop("service_areas", None)
        original_values = {field: getattr(instance, field) for field in validated_data}
        for field, value in validated_data.items():
            setattr(instance, field, value)
        try:
            instance.full_clean(exclude={"profile_photo"})
        except DjangoValidationError as error:
            for field, value in original_values.items():
                setattr(instance, field, value)
            detail = getattr(error, "message_dict", {"detail": error.messages})
            raise serializers.ValidationError(detail) from error
        instance.save()
        if areas is not None:
            instance.service_areas.set(areas)
        if therapy_ids is not None:
            instance.competencies.exclude(therapy_id__in=therapy_ids).delete()
            for therapy_id in set(therapy_ids):
                PractitionerCompetency.objects.get_or_create(application=instance, therapy_id=therapy_id)
        return instance


class ManagerApplicationSerializer(ApplicationSerializer):
    reviewer_name = serializers.CharField(source="reviewed_by.get_full_name", read_only=True, default="")

    class Meta(ApplicationSerializer.Meta):
        exclude = ("organization",)
        read_only_fields = ApplicationSerializer.Meta.read_only_fields + ("applicant",)


class ReviewActionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("review", "correction", "approve", "reject"))
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class VerificationSerializer(serializers.Serializer):
    verified = serializers.BooleanField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, trim_whitespace=True)


class OpenToWorkSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class PublicPractitionerSerializer(serializers.ModelSerializer):
    age = serializers.SerializerMethodField()
    availability_badge = serializers.SerializerMethodField()

    def get_age(self, value):
        return derived_age(value)

    def get_availability_badge(self, value):
        return "Available with NuriPain Ease"

    display_name = serializers.CharField(source="user.get_full_name", read_only=True)
    highest_qualification = serializers.SerializerMethodField()
    experience_years = serializers.SerializerMethodField()
    experience_months = serializers.SerializerMethodField()
    languages = serializers.SerializerMethodField()
    gender = serializers.SerializerMethodField()
    bio = serializers.SerializerMethodField()
    service_area = serializers.SerializerMethodField()
    verified_services = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()
    average_rating = serializers.FloatField(read_only=True, allow_null=True)
    review_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = PractitionerProfile
        fields = (
            "id",
            "age",
            "availability_badge",
            "display_name",
            "category",
            "highest_qualification",
            "qualification_specialization",
            "experience_years",
            "experience_months",
            "gender",
            "languages",
            "bio",
            "service_area",
            "verified_services",
            "photo_url",
            "average_rating",
            "review_count",
        )

    def get_verified_services(self, value) -> list[str]:
        if value.staff_profile_id:
            return list(
                value.staff_profile.therapy_competencies.filter(is_active=True).values_list(
                    "name", flat=True
                )
            )
        return []

    def _application(self, value):
        try:
            return value.source_application
        except ObjectDoesNotExist:
            return None

    def get_highest_qualification(self, value) -> str:
        application = self._application(value)
        return value.staff_profile.qualification if value.staff_profile_id else (application.qualification_title or application.get_highest_qualification_display())

    def get_experience_years(self, value) -> int:
        application = self._application(value)
        return value.staff_profile.experience_years if value.staff_profile_id else application.experience_years

    def get_experience_months(self, value) -> int:
        application = self._application(value)
        return value.staff_profile.experience_months if value.staff_profile_id else application.experience_months

    def get_languages(self, value) -> list[str]:
        application = self._application(value)
        return value.staff_profile.languages_known if value.staff_profile_id else application.languages

    def get_gender(self, value) -> str:
        application = self._application(value)
        return value.staff_profile.get_gender_display() if value.staff_profile_id else application.get_gender_display()

    def get_bio(self, value) -> str:
        application = self._application(value)
        return value.staff_profile.bio if value.staff_profile_id else application.bio

    def get_service_area(self, value) -> str:
        application = self._application(value)
        return ", ".join(value.staff_profile.service_areas.values_list("name", flat=True)) if value.staff_profile_id else application.city

    def get_photo_url(self, value) -> str:
        from apps.staff.photos import profile_photo
        application = self._application(value)
        photo = profile_photo(value.staff_profile) if value.staff_profile_id else getattr(application, "profile_photo", None)
        return f"/api/practitioners/public/{value.pk}/photo" if photo else ""
