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
            raise serializers.ValidationError("Select an approved JeevaSetu service.")
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
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Profile photographs must not exceed 5 MB.")
        if getattr(value, "content_type", "") not in ("image/jpeg", "image/png", "image/webp"):
            raise serializers.ValidationError("Upload a JPEG, PNG, or WebP photograph.")
        return value


class ApplicationSerializer(serializers.ModelSerializer):
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
        if value is None:
            return value
        today = timezone.localdate()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18 or age > 85:
            raise serializers.ValidationError("Applicants must be between 18 and 85 years old.")
        return value

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
        value = PractitionerApplication(
            applicant=self.context["request"].user,
            organization=self.context["request"].organization,
            **validated_data,
        )
        value.full_clean()
        value.save()
        return value

    def update(self, instance, validated_data):
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


class OpenToWorkSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()


class PublicPractitionerSerializer(serializers.ModelSerializer):
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
        return application.get_highest_qualification_display() if application else value.staff_profile.qualification

    def get_experience_years(self, value) -> int:
        application = self._application(value)
        return application.experience_years if application else value.staff_profile.experience_years

    def get_experience_months(self, value) -> int:
        application = self._application(value)
        return application.experience_months if application else value.staff_profile.experience_months

    def get_languages(self, value) -> list[str]:
        application = self._application(value)
        return application.languages if application else value.staff_profile.languages_known

    def get_gender(self, value) -> str:
        application = self._application(value)
        return application.get_gender_display() if application else value.staff_profile.get_gender_display()

    def get_bio(self, value) -> str:
        application = self._application(value)
        return application.bio if application else value.staff_profile.bio

    def get_service_area(self, value) -> str:
        application = self._application(value)
        return application.city if application else value.staff_profile.city

    def get_photo_url(self, value) -> str:
        request = self.context.get("request")
        path = f"/api/v1/practitioners/public/{value.pk}/photo/"
        return request.build_absolute_uri(path) if request else path
