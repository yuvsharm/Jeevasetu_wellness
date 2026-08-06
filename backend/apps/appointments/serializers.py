from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Role, RoleAssignment
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentRequest,
    TherapyOption,
)
from apps.appointments.scheduling import save_scheduled_appointment
from apps.patients.models import PatientProfile
from apps.staff.models import StaffProfile


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


class AppointmentListSerializer(serializers.ModelSerializer):
    patient_identifier = serializers.CharField(source="patient.patient_identifier", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = Appointment
        fields = (
            "id",
            "patient_identifier",
            "patient_name",
            "therapy_name",
            "clinic_name",
            "scheduled_start",
            "scheduled_end",
            "duration_minutes",
            "status",
            "physiotherapist_name",
        )


class AppointmentDetailSerializer(AppointmentListSerializer):
    profile_photo_url = serializers.SerializerMethodField()

    class Meta(AppointmentListSerializer.Meta):
        fields = AppointmentListSerializer.Meta.fields + (
            "originating_request",
            "patient",
            "therapy",
            "clinic",
            "physiotherapist",
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "operational_notes",
            "profile_photo_url",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "originating_request", "created_at", "updated_at")

    def get_profile_photo_url(self, value) -> str | None:
        if not value.physiotherapist or not value.physiotherapist.profile_photo:
            return None
        request = self.context.get("request")
        path = f"/api/v1/staff/profiles/{value.physiotherapist_id}/photo/"
        return request.build_absolute_uri(path) if request else path


class PhysiotherapistAppointmentSerializer(AppointmentListSerializer):
    class Meta(AppointmentListSerializer.Meta):
        fields = AppointmentListSerializer.Meta.fields + (
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
        )


class CustomerAppointmentSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True, default=None
    )
    physiotherapist_photo_url = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            "id",
            "scheduled_start",
            "scheduled_end",
            "therapy_name",
            "status",
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "physiotherapist_name",
            "physiotherapist_photo_url",
        )

    def get_physiotherapist_photo_url(self, value) -> str | None:
        if not value.physiotherapist or not value.physiotherapist.profile_photo:
            return None
        request = self.context.get("request")
        path = f"/api/v1/appointments/schedule/{value.pk}/physiotherapist-photo/"
        return request.build_absolute_uri(path) if request else path


class AppointmentWriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Appointment
        fields = (
            "id",
            "patient",
            "therapy",
            "clinic",
            "physiotherapist",
            "scheduled_start",
            "duration_minutes",
            "status",
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "operational_notes",
        )
        read_only_fields = ("id",)
        extra_kwargs = {"duration_minutes": {"required": False}}

    def validate(self, attrs):
        request = self.context["request"]
        organization = request.organization
        clinic = attrs.get("clinic", getattr(self.instance, "clinic", None))
        patient = attrs.get("patient", getattr(self.instance, "patient", None))
        therapy = attrs.get("therapy", getattr(self.instance, "therapy", None))
        physiotherapist = attrs.get(
            "physiotherapist", getattr(self.instance, "physiotherapist", None)
        )
        if not clinic or clinic.organization_id != organization.id or not clinic.is_active:
            raise serializers.ValidationError({"clinic": "The selected clinic is unavailable."})
        if (
            not patient
            or patient.organization_id != organization.id
            or patient.clinic_id != clinic.id
            or not patient.is_active
        ):
            raise serializers.ValidationError({"patient": "The selected patient is unavailable."})
        if not therapy or therapy.organization_id != organization.id or not therapy.is_active:
            raise serializers.ValidationError({"therapy": "The selected therapy is unavailable."})
        if physiotherapist and (
            physiotherapist.organization_id != organization.id
            or physiotherapist.clinic_id != clinic.id
            or physiotherapist.staff_type != "PHYSIOTHERAPIST"
            or not RoleAssignment.objects.filter(
                user=physiotherapist.user,
                organization=organization,
                clinic=clinic,
                role=Role.PHYSIOTHERAPIST,
                is_active=True,
            ).exists()
        ):
            raise serializers.ValidationError(
                {"physiotherapist": "The selected Physiotherapist is unavailable."}
            )
        if (
            self.instance
            and self.instance.status
            in (
                Appointment.Status.IN_PROGRESS,
                *Appointment.FINAL_STATUSES,
            )
            and any(field in attrs for field in ("scheduled_start", "duration_minutes", "clinic"))
        ):
            raise serializers.ValidationError("This appointment cannot be rescheduled.")
        if self.instance and "status" in attrs and attrs["status"] != self.instance.status:
            raise serializers.ValidationError("Use the appointment status workflow.")
        if (
            self.instance
            and "physiotherapist" in attrs
            and attrs["physiotherapist"] != self.instance.physiotherapist
        ):
            raise serializers.ValidationError("Use the assignment workflow.")
        if self.instance is None and attrs.get("status") not in (
            Appointment.Status.DRAFT,
            Appointment.Status.PENDING_ASSIGNMENT,
            Appointment.Status.SCHEDULED,
        ):
            raise serializers.ValidationError("Select a valid initial appointment status.")
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        therapy = validated_data["therapy"]
        validated_data.setdefault("duration_minutes", therapy.default_duration_minutes or 60)
        appointment = Appointment(
            organization=request.organization,
            created_by=request.user,
            updated_by=request.user,
            scheduled_end=validated_data["scheduled_start"],
            **validated_data,
        )
        try:
            return save_scheduled_appointment(
                appointment,
                actor=request.user,
                event=AppointmentAuditEvent.Event.CREATED,
            )
        except Exception as error:
            raise serializers.ValidationError(str(error)) from error

    def update(self, instance, validated_data):
        request = self.context["request"]
        previous_start = instance.scheduled_start
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.updated_by = request.user
        try:
            value = save_scheduled_appointment(
                instance,
                actor=request.user,
                event=AppointmentAuditEvent.Event.RESCHEDULED,
            )
            audit = value.audit_events.filter(event=AppointmentAuditEvent.Event.RESCHEDULED).latest(
                "created_at"
            )
            audit.previous_start = previous_start
            audit.save(update_fields=("previous_start",))
            return value
        except Exception as error:
            raise serializers.ValidationError(str(error)) from error


class ConvertRequestSerializer(AppointmentWriteSerializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=PatientProfile.objects.all())


class AssignmentSerializer(serializers.Serializer):
    physiotherapist = serializers.PrimaryKeyRelatedField(queryset=StaffProfile.objects.all())
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AppointmentStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.Status.choices)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AvailabilityQuerySerializer(serializers.Serializer):
    clinic = serializers.UUIDField()
    scheduled_start = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=30, max_value=180, default=60)
