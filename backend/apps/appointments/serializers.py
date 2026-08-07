from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Role, RoleAssignment
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentChangeRequest,
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
            "preferred_practitioner",
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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        preferred = attrs.get("preferred_practitioner")
        therapy = attrs.get("therapy")
        if preferred and (
            preferred.organization_id != self.context["request"].organization.id
            or not preferred.is_approved
            or not preferred.is_publicly_visible
            or not preferred.source_application.competencies.filter(
                therapy=therapy, verification_status="VERIFIED"
            ).exists()
        ):
            raise serializers.ValidationError(
                {"preferred_practitioner": "Select a verified practitioner for this service."}
            )
        return attrs

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
            raise serializers.ValidationError("Owners and Managers may approve or reject requests.")
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


class VisitVerificationStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=("NOT_READY", "AWAITING_VERIFICATION", "VERIFIED", "EXPIRED", "LOCKED")
    )
    verified_at = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField(allow_null=True)
    failed_attempt_warning = serializers.BooleanField()


class AppointmentListSerializer(serializers.ModelSerializer):
    patient_identifier = serializers.CharField(source="patient.patient_identifier", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True, default=None
    )
    assigned_manager_name = serializers.CharField(
        source="assigned_by.get_full_name", read_only=True, default=None
    )
    visit_verification = serializers.SerializerMethodField()

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
            "assignment_status",
            "assigned_manager_name",
            "reschedule_count",
            "cancellation_category",
            "visit_verification",
        )

    @extend_schema_field(VisitVerificationStatusSerializer)
    def get_visit_verification(self, value):
        from apps.appointments.visit_verification import visit_verification_status

        request = self.context.get("request")
        actor = request.user if request and request.user.is_authenticated else None
        return visit_verification_status(value, actor=actor)


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
            "manager_remarks",
            "assignment_rejection_reason",
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
    patient_mobile = serializers.CharField(source="patient.mobile_number", read_only=True)
    problem_description = serializers.CharField(
        source="originating_request.problem_description", read_only=True, default=""
    )

    class Meta(AppointmentListSerializer.Meta):
        fields = AppointmentListSerializer.Meta.fields + (
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "patient_mobile",
            "problem_description",
            "manager_remarks",
            "assignment_rejection_reason",
        )


class CustomerAppointmentSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True, default=None
    )
    physiotherapist_photo_url = serializers.SerializerMethodField()
    physiotherapist_qualification = serializers.CharField(
        source="physiotherapist.qualification", read_only=True, default=""
    )
    physiotherapist_experience_years = serializers.IntegerField(
        source="physiotherapist.experience_years", read_only=True, default=None
    )
    visit_verification = serializers.SerializerMethodField()

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
            "physiotherapist_qualification",
            "physiotherapist_experience_years",
            "assignment_status",
            "manager_remarks",
            "cancellation_category",
            "visit_verification",
        )

    def get_physiotherapist_photo_url(self, value) -> str | None:
        if not value.physiotherapist or not value.physiotherapist.profile_photo:
            return None
        request = self.context.get("request")
        path = f"/api/v1/appointments/schedule/{value.pk}/physiotherapist-photo/"
        return request.build_absolute_uri(path) if request else path

    @extend_schema_field(VisitVerificationStatusSerializer)
    def get_visit_verification(self, value):
        from apps.appointments.visit_verification import visit_verification_status

        request = self.context.get("request")
        actor = request.user if request and request.user.is_authenticated else None
        return visit_verification_status(value, actor=actor)


class VisitOtpSubmissionSerializer(serializers.Serializer):
    otp = serializers.RegexField(r"^\d{6}$", write_only=True)


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
            "manager_remarks",
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
                user__is_active=True,
                user__is_enabled=True,
                organization=organization,
                clinic=clinic,
                role=Role.PHYSIOTHERAPIST,
                is_active=True,
                organization_membership__is_active=True,
                clinic_membership__is_active=True,
            ).exists()
        ):
            raise serializers.ValidationError(
                {"physiotherapist": "The selected Physiotherapist is unavailable."}
            )
        if self.instance and any(
            field in attrs for field in ("scheduled_start", "duration_minutes", "clinic")
        ):
            raise serializers.ValidationError("Use the appointment rescheduling workflow.")
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
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.updated_by = request.user
        try:
            instance.full_clean()
            instance.save()
            return instance
        except Exception as error:
            raise serializers.ValidationError(str(error)) from error


class ConvertRequestSerializer(AppointmentWriteSerializer):
    patient = serializers.PrimaryKeyRelatedField(queryset=PatientProfile.objects.all())


class AssignmentSerializer(serializers.Serializer):
    physiotherapist = serializers.PrimaryKeyRelatedField(queryset=StaffProfile.objects.all())
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class UnassignmentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, trim_whitespace=True)

    def validate_reason(self, value):
        if len(value) < 3:
            raise serializers.ValidationError("A short operational reason is required.")
        return value


class AssignmentResponseSerializer(serializers.Serializer):
    accept = serializers.BooleanField()
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AppointmentChangeRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppointmentChangeRequest
        fields = ("id", "appointment", "kind", "requested_start", "reason", "status", "created_at")
        read_only_fields = ("id", "appointment", "status", "created_at")

    def validate(self, attrs):
        if attrs["kind"] == AppointmentChangeRequest.Kind.RESCHEDULE and not attrs.get(
            "requested_start"
        ):
            raise serializers.ValidationError(
                {"requested_start": "A preferred date and time is required."}
            )
        if len(attrs["reason"].strip()) < 3:
            raise serializers.ValidationError({"reason": "Provide a short reason."})
        return attrs


class AppointmentStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Appointment.Status.choices)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AvailabilityQuerySerializer(serializers.Serializer):
    clinic = serializers.UUIDField()
    scheduled_start = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=30, max_value=180, default=60)


class PhysiotherapistWorkloadSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    full_name = serializers.CharField()
    clinic = serializers.CharField()
    active_assignments = serializers.IntegerField()
    upcoming_assignments = serializers.IntegerField()


class AppointmentRescheduleSerializer(serializers.Serializer):
    scheduled_start = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=30, max_value=180)
    override = serializers.BooleanField(default=False)
    override_reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class AppointmentCancellationSerializer(serializers.Serializer):
    reason_category = serializers.ChoiceField(choices=Appointment.CancellationCategory.choices)
    operational_reason = serializers.CharField(max_length=255, trim_whitespace=True)
    override = serializers.BooleanField(default=False)
    override_reason = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def validate_operational_reason(self, value):
        if len(value.strip()) < 3:
            raise serializers.ValidationError("Provide a short operational reason.")
        return value.strip()


class AppointmentAuditSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.get_full_name", read_only=True)
    previous_physiotherapist_name = serializers.CharField(
        source="previous_physiotherapist.user.get_full_name", read_only=True, default=None
    )
    new_physiotherapist_name = serializers.CharField(
        source="new_physiotherapist.user.get_full_name", read_only=True, default=None
    )

    class Meta:
        model = AppointmentAuditEvent
        fields = (
            "id",
            "event",
            "outcome",
            "actor_name",
            "previous_status",
            "new_status",
            "previous_start",
            "new_start",
            "previous_physiotherapist_name",
            "new_physiotherapist_name",
            "reason_category",
            "reason",
            "override_used",
            "override_reason",
            "rejection_code",
            "created_at",
        )
