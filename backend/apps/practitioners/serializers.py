from pathlib import Path

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
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
}
MAX_UPLOAD_BYTES = 8 * 1024 * 1024


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
            raise serializers.ValidationError("Files must not exceed 8 MB.")
        if content_type not in ALLOWED_UPLOADS or suffix not in ALLOWED_UPLOADS[content_type]:
            raise serializers.ValidationError("Upload a PDF, JPEG, or PNG file.")
        header = value.read(8)
        value.seek(0)
        valid_signature = (
            header.startswith(b"%PDF-")
            or header.startswith(b"\xff\xd8\xff")
            or header.startswith(b"\x89PNG\r\n\x1a\n")
        )
        if not valid_signature:
            raise serializers.ValidationError("The file content does not match an allowed format.")
        return value

    def create(self, validated_data):
        file = validated_data["file"]
        return PractitionerDocument.objects.create(
            application=self.context["application"],
            kind=validated_data["kind"],
            file=file,
            original_name=Path(file.name).name[:255],
            content_type=file.content_type,
            size_bytes=file.size,
            checksum_sha256=upload_checksum(file),
        )


class ProfilePhotoUploadSerializer(serializers.Serializer):
    profile_photo = serializers.ImageField()

    def validate_profile_photo(self, value):
        if value.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Profile photographs must not exceed 5 MB.")
        if getattr(value, "content_type", "") not in ("image/jpeg", "image/png"):
            raise serializers.ValidationError("Upload a JPEG or PNG photograph.")
        return value


class ApplicationSerializer(serializers.ModelSerializer):
    competencies = CompetencySerializer(many=True, read_only=True)
    documents = DocumentMetadataSerializer(many=True, read_only=True)

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
        )

    def validate_date_of_birth(self, value):
        today = timezone.localdate()
        age = today.year - value.year - ((today.month, today.day) < (value.month, value.day))
        if age < 18 or age > 85:
            raise serializers.ValidationError("Applicants must be between 18 and 85 years old.")
        return value

    def validate_passing_year(self, value):
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


class ManagerApplicationSerializer(ApplicationSerializer):
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
    highest_qualification = serializers.CharField(
        source="source_application.get_highest_qualification_display", read_only=True
    )
    experience_years = serializers.IntegerField(
        source="source_application.experience_years", read_only=True
    )
    languages = serializers.JSONField(source="source_application.languages", read_only=True)
    bio = serializers.CharField(source="source_application.bio", read_only=True)
    service_area = serializers.CharField(source="source_application.city", read_only=True)
    verified_services = serializers.SerializerMethodField()
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = PractitionerProfile
        fields = (
            "id",
            "display_name",
            "category",
            "highest_qualification",
            "qualification_specialization",
            "experience_years",
            "languages",
            "bio",
            "service_area",
            "verified_services",
            "photo_url",
        )

    def get_verified_services(self, value) -> list[str]:
        return list(
            value.source_application.competencies.filter(
                verification_status="VERIFIED"
            ).values_list("therapy__name", flat=True)
        )

    def get_photo_url(self, value) -> str:
        request = self.context.get("request")
        path = f"/api/v1/practitioners/public/{value.pk}/photo/"
        return request.build_absolute_uri(path) if request else path
