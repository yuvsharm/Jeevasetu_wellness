from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.appointments.models import AppointmentRequest, TherapyOption


class TherapyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TherapyOption
        fields = ("id", "name", "slug")


class AppointmentRequestSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)

    class Meta:
        model = AppointmentRequest
        fields = (
            "id",
            "therapy",
            "therapy_name",
            "patient_name",
            "age",
            "gender",
            "mobile_number",
            "alternate_mobile",
            "email",
            "session_preference",
            "preferred_date",
            "preferred_time",
            "problem_description",
            "pain_area",
            "problem_duration",
            "doctor_reference",
            "address",
            "city",
            "pin_code",
            "landmark",
            "google_map_link",
            "status",
            "owner_remarks",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "therapy_name",
            "status",
            "owner_remarks",
            "created_at",
            "updated_at",
        )

    def validate_preferred_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("Preferred date cannot be in the past.")
        return value

    def validate_therapy(self, value):
        organization = self.context["request"].organization
        if not value.is_active or value.organization_id != organization.id:
            raise serializers.ValidationError("Select an active therapy.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        user = getattr(request, "user", None)
        value = AppointmentRequest(
            organization=request.organization,
            creator=user if user and user.is_authenticated else None,
            **validated_data,
        )
        value.duplicate_fingerprint = value.build_fingerprint()
        try:
            with transaction.atomic():
                value.full_clean(exclude=("duplicate_fingerprint",))
                value.save()
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"detail": "An identical pending appointment request already exists."}
            ) from error
        return value


class OwnerAppointmentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppointmentRequest
        fields = ("status", "owner_remarks")

    def validate_status(self, value):
        if value not in (AppointmentRequest.Status.APPROVED, AppointmentRequest.Status.REJECTED):
            raise serializers.ValidationError("Owners may approve or reject requests.")
        return value


class CancelAppointmentSerializer(serializers.Serializer):
    def update(self, instance, validated_data):
        if instance.status != AppointmentRequest.Status.PENDING:
            raise serializers.ValidationError("Only pending requests can be cancelled.")
        instance.status = AppointmentRequest.Status.CANCELLED
        instance.save(update_fields=("status", "updated_at"))
        return instance

    def create(self, validated_data):
        raise NotImplementedError
