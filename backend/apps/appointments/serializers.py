from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import RegexValidator
from django.db import IntegrityError, transaction
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.accounts.models import Role, RoleAssignment
from apps.accounts.role_policy import actor_role_scope
from apps.appointments.booking_verification import resolve_booking_verification
from apps.appointments.commercial import calculate_quote
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentChangeRequest,
    AppointmentPayment,
    AppointmentRequest,
    AppointmentRequestAuditEvent,
    AppointmentRating,
    CommercialOffer,
    PractitionerPayment,
    TherapyOption,
    TherapyPackage,
)
from apps.appointments.scheduling import save_scheduled_appointment, validate_schedule
from apps.availability.services import discover_slots
from apps.patients.models import CustomerFamilyMember, PatientAddress, PatientProfile
from apps.staff.models import StaffProfile
from apps.tenancy.models import Clinic


class TherapyOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TherapyOption
        fields = ("id", "name", "slug")


class TherapyCommercialSerializer(serializers.ModelSerializer):
    can_delete = serializers.SerializerMethodField()
    protected_references = serializers.SerializerMethodField()

    class Meta:
        model = TherapyOption
        fields = ("id", "name", "slug", "short_description", "detailed_description", "benefits", "default_duration_minutes", "base_price", "is_active", "is_publicly_visible", "is_offer_free_addon", "display_order", "can_delete", "protected_references")
        read_only_fields = ("id", "can_delete", "protected_references")

    def get_can_delete(self, value):
        return value.can_be_deleted()

    def get_protected_references(self, value):
        return value.protected_reference_summary()

    def validate(self, attrs):
        offer_only = attrs.get("is_offer_free_addon", getattr(self.instance, "is_offer_free_addon", False))
        duration = attrs.get("default_duration_minutes", getattr(self.instance, "default_duration_minutes", None))
        required_duration = 15 if offer_only else 45
        if duration not in (None, required_duration):
            raise serializers.ValidationError({
                "default_duration_minutes": f"{'Offer-only add-ons use' if offer_only else 'Production scheduling uses exactly'} {required_duration} minutes."
            })
        attrs["default_duration_minutes"] = required_duration
        return attrs


class TherapyPackageSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    regular_total = serializers.SerializerMethodField()
    saving = serializers.SerializerMethodField()
    discount_percentage = serializers.SerializerMethodField()

    class Meta:
        model = TherapyPackage
        fields = ("id", "name", "therapy", "therapy_name", "session_count", "selling_price", "regular_total", "saving", "discount_percentage", "description", "valid_from", "valid_until", "is_active", "is_publicly_visible", "display_order")

    def get_regular_total(self, value):
        return value.therapy.base_price * value.session_count

    def get_saving(self, value):
        return max(0, self.get_regular_total(value) - value.selling_price)

    def get_discount_percentage(self, value):
        regular = self.get_regular_total(value)
        return round(self.get_saving(value) * 100 / regular, 2) if regular else 0

    def validate(self, attrs):
        value = self.instance or TherapyPackage(organization=self.context["request"].organization)
        for key, item in attrs.items():
            setattr(value, key, item)
        try:
            value.full_clean(exclude=("id",))
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        return attrs


class CommercialOfferSerializer(serializers.ModelSerializer):
    eligible_therapy_names = serializers.SerializerMethodField()
    free_therapy_name = serializers.CharField(source="free_therapy.name", read_only=True, default="")
    can_delete = serializers.SerializerMethodField()
    protected_references = serializers.SerializerMethodField()

    class Meta:
        model = CommercialOffer
        fields = ("id", "title", "promotional_text", "offer_type", "eligible_therapies", "eligible_therapy_names", "qualifying_package", "minimum_therapy_count", "maximum_therapy_count", "discount_value", "fixed_price", "free_therapy", "free_therapy_name", "free_quantity", "family_required", "minimum_family_members", "rule_config", "valid_from", "valid_until", "is_active", "is_publicly_visible", "display_order", "created_at", "updated_at", "can_delete", "protected_references")
        read_only_fields = ("id", "created_at", "updated_at", "can_delete", "protected_references")

    def get_eligible_therapy_names(self, value):
        return list(value.eligible_therapies.values_list("name", flat=True))

    def get_can_delete(self, value):
        return value.can_be_deleted()

    def get_protected_references(self, value):
        return value.protected_reference_summary()

    def validate(self, attrs):
        value = self.instance or CommercialOffer(organization=self.context["request"].organization)
        for key, item in attrs.items():
            if key != "eligible_therapies":
                setattr(value, key, item)
        if value.is_active and value.valid_until and value.valid_until <= timezone.now():
            raise serializers.ValidationError({"valid_until": "Edit the offer end date to a future date before reactivating it." if self.instance and attrs.get("is_active") else "Offer end date must be in the future."})
        try:
            value.full_clean(exclude=("id",))
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        therapies = attrs.get("eligible_therapies", getattr(self.instance, "eligible_therapies", TherapyOption.objects.none()).all() if self.instance else [])
        organization_id = self.context["request"].organization.id
        if any(item.organization_id != organization_id for item in therapies):
            raise serializers.ValidationError({"eligible_therapies": "Select therapies from this organization only."})
        if value.is_active and any(not item.is_active for item in therapies):
            raise serializers.ValidationError({"eligible_therapies": "Reactivate the selected therapies before activating this offer."})
        if any(item.is_offer_free_addon for item in therapies):
            raise serializers.ValidationError({"eligible_therapies": "Offer-only free add-ons cannot be selected as paid therapies."})
        free_therapy = attrs.get("free_therapy", getattr(self.instance, "free_therapy", None))
        if free_therapy and free_therapy.organization_id != organization_id:
            raise serializers.ValidationError({"free_therapy": "Select a therapy from this organization only."})
        free_offer = value.offer_type in (CommercialOffer.OfferType.FREE_THERAPY, CommercialOffer.OfferType.FAMILY_FREE)
        if value.is_active and free_offer and free_therapy and not free_therapy.is_active:
            raise serializers.ValidationError({"free_therapy": "Reactivate the free therapy before activating this offer."})
        if free_offer and free_therapy and str(free_therapy.id) in {str(item.id) for item in therapies}:
            raise serializers.ValidationError({"free_therapy": "The free therapy must be different from the paid therapies."})
        qualifying_package = attrs.get("qualifying_package", getattr(self.instance, "qualifying_package", None))
        if qualifying_package and qualifying_package.organization_id != organization_id:
            raise serializers.ValidationError({"qualifying_package": "Select a package from this organization only."})
        if not therapies:
            raise serializers.ValidationError({"eligible_therapies": "Please select at least one therapy."})
        eligible_ids = {str(item.id) for item in therapies}
        for rule in attrs.get("rule_config", {}).get("therapy_discounts", []):
            if str(rule.get("therapy_id")) not in eligible_ids:
                raise serializers.ValidationError({"rule_config": "Discount rules must use selected therapies."})
        return attrs


class CommercialQuoteSerializer(serializers.Serializer):
    therapy_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    package_id = serializers.UUIDField(required=False, allow_null=True)
    offer_id = serializers.UUIDField(required=False, allow_null=True)
    family_member_id = serializers.UUIDField(required=False, allow_null=True)
    service_at = serializers.DateTimeField(required=False, allow_null=True)


class BookingOtpRequestSerializer(serializers.Serializer):
    mobile_number = serializers.CharField(
        max_length=10,
        min_length=10,
        validators=[RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")],
    )


class BookingOtpVerifySerializer(serializers.Serializer):
    verification_id = serializers.UUIDField()
    mobile_number = serializers.CharField(
        max_length=10,
        min_length=10,
        validators=[RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")],
    )
    otp = serializers.RegexField(r"^\d{6}$", required=False, write_only=True)
    access_token = serializers.CharField(required=False, write_only=True, trim_whitespace=False, max_length=4096)

    def validate(self, attrs):
        required = "access_token" if settings.MSG91_ENABLED else "otp"
        if not attrs.get(required):
            raise serializers.ValidationError({required: "This field is required for mobile verification."})
        return attrs


class CustomerRebookSerializer(serializers.Serializer):
    preferred_date = serializers.DateField()
    preferred_time = serializers.TimeField()


class OwnerAppointmentRebookSerializer(CustomerRebookSerializer):
    physiotherapist = serializers.PrimaryKeyRelatedField(queryset=StaffProfile.objects.all())


class AppointmentRequestSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    requested_therapy_names = serializers.SerializerMethodField()
    requested_duration_minutes = serializers.IntegerField(read_only=True)
    booking_verification_token = serializers.CharField(write_only=True, required=False)
    requested_therapies = serializers.PrimaryKeyRelatedField(
        queryset=TherapyOption.objects.all(), many=True, required=False, allow_empty=True
    )
    family_member = serializers.PrimaryKeyRelatedField(
        queryset=CustomerFamilyMember.objects.all(), required=False, allow_null=True
    )
    selected_package = serializers.PrimaryKeyRelatedField(queryset=TherapyPackage.objects.all(), required=False, allow_null=True)
    selected_offer = serializers.PrimaryKeyRelatedField(queryset=CommercialOffer.objects.all(), required=False, allow_null=True)

    class Meta:
        model = AppointmentRequest
        fields = (
            "id",
            "therapy",
            "requested_therapies",
            "requested_therapy_names",
            "requested_duration_minutes",
            "family_member",
            "selected_package",
            "selected_offer",
            "commercial_snapshot",
            "regular_amount",
            "discount_amount",
            "final_amount",
            "booking_verification_token",
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
            "region",
            "pin_code",
            "landmark",
            "google_map_link",
            "latitude",
            "longitude",
            "location_accuracy_meters",
            "location_source",
            "status",
            "owner_remarks",
            "booking_source",
            "rejection_category",
            "rejection_customer_reason",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "therapy_name",
            "status",
            "owner_remarks",
            "booking_source",
            "rejection_category",
            "rejection_customer_reason",
            "created_at",
            "updated_at",
            "commercial_snapshot",
            "regular_amount",
            "discount_amount",
            "final_amount",
        )
        extra_kwargs = {
            "latitude": {"write_only": True},
            "longitude": {"write_only": True},
            "location_accuracy_meters": {"write_only": True},
        }

    def validate_preferred_date(self, value):
        if value < timezone.localdate():
            raise serializers.ValidationError("Preferred date cannot be in the past.")
        return value

    def get_requested_therapy_names(self, value):
        return [value.therapy.name, *value.requested_therapies.values_list("name", flat=True)]

    def validate_therapy(self, value):
        organization = self.context["request"].organization
        if (
            not value.is_active
            or not value.is_publicly_visible
            or value.is_offer_free_addon
            or value.organization_id != organization.id
        ):
            raise serializers.ValidationError("Select an available bookable therapy.")
        return value

    def validate_requested_therapies(self, value):
        organization = self.context["request"].organization
        for therapy in value:
            if (
                not therapy.is_active
                or not therapy.is_publicly_visible
                or therapy.is_offer_free_addon
                or therapy.organization_id != organization.id
            ):
                raise serializers.ValidationError(
                    "Select only available bookable therapies in this organization."
                )
        if len(value) > 8:
            raise serializers.ValidationError("Select up to eight therapy preferences.")
        return list(dict.fromkeys(value))

    def validate(self, attrs):
        attrs = super().validate(attrs)
        token = attrs.get("booking_verification_token")
        if self.context.get("require_booking_verification"):
            if not token:
                raise serializers.ValidationError(
                    {"booking_verification_token": "Please verify your mobile number before booking."}
                )
            try:
                resolve_booking_verification(
                    organization=self.context["request"].organization,
                    mobile_number=attrs.get("mobile_number"),
                    token=token,
                )
            except DjangoValidationError as error:
                raise serializers.ValidationError(
                    {"booking_verification_token": error.messages}
                ) from error
        preferred = attrs.get("preferred_practitioner")
        therapy = attrs.get("therapy")
        requested = list(attrs.get("requested_therapies", []))
        if therapy and any(item.id == therapy.id for item in requested):
            requested = [item for item in requested if item.id != therapy.id]
            attrs["requested_therapies"] = requested
        duration = (1 + len(requested)) * 45
        start = datetime.combine(attrs["preferred_date"], attrs["preferred_time"])
        if start.time().strftime("%H:%M") < "09:00" or start + timedelta(minutes=duration) > datetime.combine(attrs["preferred_date"], datetime.strptime("18:00", "%H:%M").time()):
            raise serializers.ValidationError({"preferred_time": "Select a start time from 9:00 AM that allows all selected therapies to finish by 6:00 PM."})
        family = attrs.get("family_member")
        actor = getattr(self.context["request"], "user", None)
        if family and (not actor or not actor.is_authenticated or family.customer_id != actor.id or family.organization_id != self.context["request"].organization.id or not family.is_active):
            raise serializers.ValidationError({"family_member": "The selected family member is unavailable."})
        if family:
            attrs.update(patient_name=family.full_name, age=family.age, gender=family.gender)
        try:
            self._commercial_quote = calculate_quote(
                organization=self.context["request"].organization,
                therapy_ids=[therapy.id, *[item.id for item in requested]],
                package_id=getattr(attrs.get("selected_package"), "id", None),
                offer_id=getattr(attrs.get("selected_offer"), "id", None),
                family_member=family,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        duration = self._commercial_quote.duration_minutes
        if start + timedelta(minutes=duration) > datetime.combine(attrs["preferred_date"], datetime.strptime("18:00", "%H:%M").time()):
            raise serializers.ValidationError({"preferred_time": "This selection, including free performed therapies, must finish by 6:00 PM."})
        if preferred and (
            preferred.organization_id != self.context["request"].organization.id
            or not preferred.is_approved
            or not preferred.is_publicly_visible
            or preferred.staff_profile_id is None
            or not preferred.staff_profile.therapy_competencies.filter(pk=therapy.pk).exists()
        ):
            raise serializers.ValidationError(
                {"preferred_practitioner": "Select a practitioner who currently offers this service."}
            )
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        user = getattr(request, "user", None)
        verification_token = validated_data.pop("booking_verification_token", None)
        requested_therapies = validated_data.pop("requested_therapies", [])
        value = AppointmentRequest(
            organization=request.organization,
            creator=user if user and user.is_authenticated else None,
            **validated_data,
        )
        value.duplicate_fingerprint = value.build_fingerprint()
        try:
            with transaction.atomic():
                verification = None
                if verification_token:
                    verification = resolve_booking_verification(
                        organization=request.organization,
                        mobile_number=validated_data["mobile_number"],
                        token=verification_token,
                        lock=True,
                    )
                value.full_clean(exclude=("duplicate_fingerprint",))
                quote = calculate_quote(
                    organization=request.organization,
                    therapy_ids=[validated_data["therapy"].id, *[item.id for item in requested_therapies]],
                    package_id=getattr(validated_data.get("selected_package"), "id", None),
                    offer_id=getattr(validated_data.get("selected_offer"), "id", None),
                    family_member=validated_data.get("family_member"),
                )
                value.commercial_snapshot = quote.snapshot()
                value.regular_amount = quote.regular_amount
                value.discount_amount = quote.discount_amount
                value.final_amount = quote.final_amount
                value.selected_offer_id = quote.offer_id
                value.save()
                all_additional = list(requested_therapies)
                free_ids = [benefit["therapy_id"] for benefit in quote.free_benefits]
                all_additional.extend(TherapyOption.objects.filter(id__in=free_ids).exclude(id=value.therapy_id))
                value.requested_therapies.set(list(dict.fromkeys(all_additional)))
                if verification:
                    verification.consumed_at = timezone.now()
                    verification.save(update_fields=("consumed_at",))
        except DjangoValidationError as error:
            raise serializers.ValidationError(
                {"booking_verification_token": error.messages}
            ) from error
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


class AppointmentListSerializer(serializers.ModelSerializer):
    patient_identifier = serializers.CharField(source="patient.patient_identifier", read_only=True)
    patient_name = serializers.SerializerMethodField()
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    clinic_name = serializers.CharField(source="clinic.name", read_only=True)
    physiotherapist_name = serializers.CharField(
        source="physiotherapist.user.get_full_name", read_only=True, default=None
    )
    assigned_manager_name = serializers.CharField(
        source="assigned_by.get_full_name", read_only=True, default=None
    )
    payment_status = serializers.SerializerMethodField()
    payment_amount_due = serializers.SerializerMethodField()
    payment_paid_at = serializers.SerializerMethodField()
    payment_confirmed_by = serializers.SerializerMethodField()
    payment_qr_available = serializers.SerializerMethodField()
    requested_therapy_names = serializers.SerializerMethodField()
    patient_mobile = serializers.SerializerMethodField()
    patient_email = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = (
            "id",
            "originating_request",
            "patient_identifier",
            "patient_name",
            "patient_mobile",
            "patient_email",
            "therapy_name",
            "requested_therapy_names",
            "clinic_name",
            "clinic",
            "scheduled_start",
            "scheduled_end",
            "duration_minutes",
            "status",
            "physiotherapist_name",
            "assignment_status",
            "assignment_rejection_reason",
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "assigned_manager_name",
            "reschedule_count",
            "cancellation_category",
            "journey_status",
            "en_route_at",
            "service_started_at",
            "completed_at",
            "payment_status",
            "payment_amount_due",
            "payment_paid_at",
            "payment_confirmed_by",
            "payment_qr_available",
            "updated_at",
        )

    def get_payment_status(self, value):
        payment = getattr(value, "payment", None)
        return payment.status if payment else None

    def get_payment_amount_due(self, value):
        payment = getattr(value, "payment", None)
        if payment:
            return payment.amount_due
        source = getattr(value, "originating_request", None)
        return source.final_amount if source and source.final_amount is not None else None

    def get_payment_paid_at(self, value):
        payment = getattr(value, "payment", None)
        return payment.paid_at if payment else None

    def get_payment_confirmed_by(self, value):
        payment = getattr(value, "payment", None)
        if not payment or payment.status != AppointmentPayment.Status.PAID:
            return ""
        return payment.updated_by.get_full_name() or payment.updated_by.get_username()

    def get_payment_qr_available(self, value):
        return bool(settings.PAYMENT_UPI_ID and settings.PAYMENT_PAYEE_NAME)


    def get_requested_therapy_names(self, value):
        source = getattr(value, "originating_request", None)
        if source is None:
            return [value.therapy.name]
        return [source.therapy.name, *source.requested_therapies.values_list("name", flat=True)]

    def get_patient_name(self, value):
        source = getattr(value, "originating_request", None)
        return source.patient_name if source and source.patient_name else value.patient.full_name

    def get_patient_mobile(self, value):
        source = getattr(value, "originating_request", None)
        return source.mobile_number if source and source.mobile_number else value.patient.mobile_number

    def get_patient_email(self, value):
        return value.patient.email or (value.patient.user.email if value.patient.user_id else "")


class AppointmentDetailSerializer(AppointmentListSerializer):
    profile_photo_url = serializers.SerializerMethodField()

    class Meta(AppointmentListSerializer.Meta):
        fields = AppointmentListSerializer.Meta.fields + (
            "patient",
            "therapy",
            "clinic",
            "physiotherapist",
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
    patient_name = serializers.SerializerMethodField()
    patient_mobile = serializers.SerializerMethodField()
    patient_age = serializers.SerializerMethodField()
    patient_gender = serializers.SerializerMethodField()
    problem_description = serializers.CharField(
        source="originating_request.problem_description", read_only=True, default=""
    )
    pain_area = serializers.CharField(source="originating_request.pain_area", read_only=True, default="")
    google_map_link = serializers.CharField(source="originating_request.google_map_link", read_only=True, default="")
    rating_stars = serializers.IntegerField(source="rating.stars", read_only=True, default=None)
    rating_comment = serializers.CharField(source="rating.comment", read_only=True, default="")
    reminders = serializers.SerializerMethodField()

    class Meta(AppointmentListSerializer.Meta):
        fields = AppointmentListSerializer.Meta.fields + (
            "address_line_1",
            "address_line_2",
            "landmark",
            "city",
            "region",
            "pin_code",
            "patient_mobile",
            "patient_age",
            "patient_gender",
            "problem_description",
            "pain_area",
            "google_map_link",
            "rating_stars",
            "rating_comment",
            "manager_remarks",
            "assignment_rejection_reason",
            "journey_status",
            "en_route_at",
            "service_started_at",
            "completed_at",
            "reminders",
        )

    def get_patient_name(self, value):
        if value.assignment_status not in (
            Appointment.AssignmentStatus.PENDING,
            Appointment.AssignmentStatus.ACCEPTED,
        ):
            return "Service request"
        return super().get_patient_name(value)

    def get_patient_mobile(self, value):
        if value.assignment_status not in (
            Appointment.AssignmentStatus.PENDING,
            Appointment.AssignmentStatus.ACCEPTED,
        ):
            return ""
        return super().get_patient_mobile(value)

    def get_patient_age(self, value):
        if value.assignment_status not in (
            Appointment.AssignmentStatus.PENDING,
            Appointment.AssignmentStatus.ACCEPTED,
        ):
            return None
        source = getattr(value, "originating_request", None)
        if source and source.age is not None:
            return source.age
        if value.patient.date_of_birth:
            today = timezone.localdate()
            return today.year - value.patient.date_of_birth.year - (
                (today.month, today.day)
                < (value.patient.date_of_birth.month, value.patient.date_of_birth.day)
            )
        return value.patient.age

    def get_patient_gender(self, value):
        if value.assignment_status not in (
            Appointment.AssignmentStatus.PENDING,
            Appointment.AssignmentStatus.ACCEPTED,
        ):
            return ""
        source = getattr(value, "originating_request", None)
        return source.gender if source and source.gender else value.patient.gender

    def get_reminders(self, value):
        return [
            {
                "kind": reminder.kind,
                "scheduled_for": reminder.scheduled_for,
                "status": reminder.status,
            }
            for reminder in value.reminders.exclude(status="CANCELLED").order_by("scheduled_for")
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.assignment_status not in (
            Appointment.AssignmentStatus.PENDING,
            Appointment.AssignmentStatus.ACCEPTED,
        ):
            for field in (
                "patient_identifier", "patient_mobile", "patient_age", "patient_gender",
                "problem_description", "pain_area", "google_map_link",
                "address_line_1", "address_line_2", "landmark", "pin_code", "manager_remarks",
            ):
                data[field] = ""
        return data


class CustomerAppointmentSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    physiotherapist_name = serializers.SerializerMethodField()
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    payment_status = serializers.SerializerMethodField()
    payment_amount_due = serializers.SerializerMethodField()
    payment_paid_at = serializers.SerializerMethodField()
    payment_confirmed_by = serializers.SerializerMethodField()
    payment_qr_available = serializers.SerializerMethodField()
    requested_therapy_names = serializers.SerializerMethodField()
    physiotherapist_photo_url = serializers.SerializerMethodField()
    physiotherapist_qualification = serializers.CharField(
        source="physiotherapist.qualification", read_only=True, default=""
    )
    physiotherapist_experience_years = serializers.IntegerField(
        source="physiotherapist.experience_years", read_only=True, default=None
    )
    physiotherapist_age = serializers.SerializerMethodField()
    physiotherapist_specialization = serializers.SerializerMethodField()
    physiotherapist_expertise = serializers.SerializerMethodField()
    physiotherapist_rating = serializers.SerializerMethodField()
    physiotherapist_review_count = serializers.SerializerMethodField()
    rating = serializers.SerializerMethodField()
    requested_at = serializers.DateTimeField(
        source="originating_request.created_at", read_only=True, default=None
    )

    class Meta:
        model = Appointment
        fields = (
            "id",
            "originating_request",
            "requested_at",
            "created_at",
            "patient_name",
            "scheduled_start",
            "scheduled_end",
            "duration_minutes",
            "therapy_name",
            "requested_therapy_names",
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
            "physiotherapist_age",
            "physiotherapist_specialization",
            "physiotherapist_expertise",
            "physiotherapist_rating",
            "physiotherapist_review_count",
            "assignment_status",
            "manager_remarks",
            "cancellation_category",
            "journey_status",
            "service_started_at",
            "completed_at",
            "payment_status",
            "payment_amount_due",
            "payment_paid_at",
            "payment_confirmed_by",
            "payment_qr_available",
            "rating",
        )
        read_only_fields = ("id", "originating_request", "requested_at", "created_at")

    def get_physiotherapist_name(self, value):
        if not self._therapist_visible(value):
            return None
        return value.physiotherapist.user.get_full_name()

    def _therapist_visible(self, value):
        return bool(
            value.physiotherapist
            and value.assignment_status in (
                Appointment.AssignmentStatus.PENDING,
                Appointment.AssignmentStatus.ACCEPTED,
            )
        )

    def get_physiotherapist_age(self, value):
        if not self._therapist_visible(value):
            return None
        from apps.practitioners.dob import derived_age
        return derived_age(value.physiotherapist)

    def get_physiotherapist_specialization(self, value):
        if not self._therapist_visible(value):
            return ""
        practitioner = getattr(value.physiotherapist, "practitioner_profile", None)
        if practitioner and practitioner.qualification_specialization:
            return practitioner.qualification_specialization
        return ", ".join(value.physiotherapist.specializations.values_list("name", flat=True))

    def get_physiotherapist_expertise(self, value):
        if not self._therapist_visible(value):
            return []
        source = value.originating_request
        ids = {value.therapy_id}
        if source:
            ids.update(source.requested_therapies.values_list("id", flat=True))
        return list(
            value.physiotherapist.therapy_competencies.filter(id__in=ids)
            .order_by("name").values_list("name", flat=True)
        )

    def _approved_ratings(self, value):
        if not self._therapist_visible(value):
            return AppointmentRating.objects.none()
        return AppointmentRating.objects.filter(
            physiotherapist=value.physiotherapist,
            moderation_status=AppointmentRating.ModerationStatus.APPROVED,
        )

    def get_physiotherapist_rating(self, value):
        from django.db.models import Avg
        return self._approved_ratings(value).aggregate(value=Avg("stars"))["value"]

    def get_physiotherapist_review_count(self, value):
        return self._approved_ratings(value).count()

    def get_rating(self, value):
        rating = getattr(value, "rating", None)
        return AppointmentRatingSerializer(rating).data if rating else None

    def get_payment_status(self, value):
        payment = getattr(value, "payment", None)
        return payment.status if payment else None

    def get_payment_amount_due(self, value):
        payment = getattr(value, "payment", None)
        if payment:
            return payment.amount_due
        source = getattr(value, "originating_request", None)
        return source.final_amount if source and source.final_amount is not None else None

    def get_payment_paid_at(self, value):
        payment = getattr(value, "payment", None)
        return payment.paid_at if payment else None

    def get_payment_confirmed_by(self, value):
        payment = getattr(value, "payment", None)
        if not payment or payment.status != AppointmentPayment.Status.PAID:
            return ""
        return payment.updated_by.get_full_name() or payment.updated_by.get_username()

    def get_payment_qr_available(self, value):
        return bool(settings.PAYMENT_UPI_ID and settings.PAYMENT_PAYEE_NAME)

    def get_requested_therapy_names(self, value):
        source = getattr(value, "originating_request", None)
        if source is None:
            return [value.therapy.name]
        return [source.therapy.name, *source.requested_therapies.values_list("name", flat=True)]

    def get_physiotherapist_photo_url(self, value) -> str | None:
        if not self._therapist_visible(value):
            return None
        from apps.staff.photos import profile_photo
        if not profile_photo(value.physiotherapist):
            return None
        request = self.context.get("request")
        path = f"/api/v1/appointments/schedule/{value.pk}/physiotherapist-photo/"
        return request.build_absolute_uri(path) if request else path

class CustomerAppointmentRequestSerializer(AppointmentRequestSerializer):
    family_member_name = serializers.CharField(
        source="family_member.full_name", read_only=True, default=""
    )
    appointment = serializers.SerializerMethodField()
    timeline = serializers.SerializerMethodField()

    class Meta(AppointmentRequestSerializer.Meta):
        fields = AppointmentRequestSerializer.Meta.fields + (
            "family_member_name", "appointment", "timeline"
        )

    def get_appointment(self, value):
        try:
            appointment = value.operational_appointment
        except Appointment.DoesNotExist:
            return None
        return CustomerAppointmentSerializer(appointment, context=self.context).data

    def get_timeline(self, value):
        result = [{"key": "SUBMITTED", "label": "Request submitted", "at": value.created_at}]
        result.append({"key": "REVIEW", "label": "Under Owner review", "at": value.created_at})
        accepted = value.audit_events.filter(
            event__in=(
                AppointmentRequestAuditEvent.Event.ACCEPTED,
                AppointmentRequestAuditEvent.Event.APPROVED_AND_ASSIGNED,
            )
        ).order_by("created_at").first()
        if value.status == AppointmentRequest.Status.REJECTED:
            rejected = value.audit_events.filter(
                event=AppointmentRequestAuditEvent.Event.REJECTED
            ).order_by("created_at").first()
            result.append({"key": "REJECTED", "label": "Request not accepted", "at": getattr(rejected, "created_at", value.updated_at)})
            return result
        if value.status == AppointmentRequest.Status.CANCELLED:
            result.append({"key": "CANCELLED", "label": "Request cancelled", "at": value.updated_at})
            return result
        if value.status == AppointmentRequest.Status.APPROVED:
            result.append({"key": "ACCEPTED", "label": "Request accepted", "at": getattr(accepted, "created_at", value.updated_at)})
        try:
            appointment = value.operational_appointment
        except Appointment.DoesNotExist:
            return result
        result.extend((
            {"key": "ASSIGNED", "label": "Therapist assigned", "at": appointment.assigned_at},
            {"key": "CONFIRMED", "label": "Appointment confirmed", "at": appointment.created_at},
        ))
        if appointment.assignment_status == Appointment.AssignmentStatus.REJECTED:
            result.append({"key": "REASSIGNMENT", "label": "Therapist reassignment in progress", "at": appointment.assignment_responded_at})
            return result
        if appointment.assignment_status == Appointment.AssignmentStatus.ACCEPTED:
            result.append({"key": "THERAPIST_ACCEPTED", "label": "Therapist confirmed", "at": appointment.assignment_responded_at})
        if appointment.en_route_at:
            result.append({"key": "EN_ROUTE", "label": "Therapist en route", "at": appointment.en_route_at})
        if appointment.service_started_at:
            result.append({"key": "IN_SERVICE", "label": "Session in progress", "at": appointment.service_started_at})
        if appointment.completed_at:
            result.append({"key": "COMPLETED", "label": "Appointment completed", "at": appointment.completed_at})
        if appointment.status in (Appointment.Status.CANCELLED, Appointment.Status.NO_SHOW):
            result.append({"key": appointment.status, "label": "Appointment closed", "at": appointment.updated_at})
        return result


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
        source = validated_data.get("originating_request")
        validated_data.setdefault(
            "duration_minutes",
            source.requested_duration_minutes if source else (therapy.default_duration_minutes or 60),
        )
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
    expected_updated_at = serializers.DateTimeField(required=False)


class UnassignmentSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, trim_whitespace=True)
    expected_updated_at = serializers.DateTimeField(required=False)

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


class AppointmentCompletionPaymentSerializer(serializers.Serializer):
    therapy_delivered = serializers.BooleanField()
    payment_received = serializers.BooleanField()

    def validate(self, attrs):
        if not attrs["therapy_delivered"] or not attrs["payment_received"]:
            raise serializers.ValidationError(
                "Confirm both therapy delivery and customer payment confirmation."
            )
        return attrs


class JourneyUpdateSerializer(serializers.Serializer):
    journey_status = serializers.ChoiceField(
        choices=(Appointment.JourneyStatus.EN_ROUTE, Appointment.JourneyStatus.REACHED)
    )


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

class AppointmentRatingSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_moderation_status_display", read_only=True)

    class Meta:
        model = AppointmentRating
        fields = ("id", "appointment", "stars", "comment", "moderation_status", "status_display", "moderation_reason", "created_at")
        read_only_fields = ("id", "appointment", "moderation_status", "status_display", "moderation_reason", "created_at")

    def validate_comment(self, value):
        value = value.strip()
        if not value:
            return ""
        if len(value) < 3:
            raise serializers.ValidationError("Please share at least 3 characters about your experience.")
        return value


class AppointmentRequestDecisionSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=("ACCEPT", "ASSIGN", "ACCEPT_ASSIGN", "REJECT"))
    physiotherapist = serializers.PrimaryKeyRelatedField(
        queryset=StaffProfile.objects.all(), required=False
    )
    rejection_category = serializers.ChoiceField(
        choices=AppointmentRequest.RejectionCategory.choices, required=False
    )
    customer_reason = serializers.CharField(max_length=255, required=False, allow_blank=True)
    internal_note = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["action"] in ("ASSIGN", "ACCEPT_ASSIGN") and not attrs.get("physiotherapist"):
            raise serializers.ValidationError(
                {"physiotherapist": "Select an eligible practitioner."}
            )
        if attrs["action"] == "REJECT":
            if not attrs.get("rejection_category"):
                raise serializers.ValidationError(
                    {"rejection_category": "Select a rejection reason."}
                )
            if len(attrs.get("customer_reason", "").strip()) < 3:
                raise serializers.ValidationError(
                    {"customer_reason": "Provide a customer-safe rejection reason."}
                )
        return attrs


class BookingServiceAddressSerializer(serializers.Serializer):
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    landmark = serializers.CharField(max_length=160, required=False, allow_blank=True)
    city = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=120)
    pin_code = serializers.RegexField(r"^[1-9]\d{5}$")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    location_accuracy_meters = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    location_source = serializers.ChoiceField(choices=PatientAddress.LocationSource.choices, required=False)


class AuthenticatedAppointmentRequestSerializer(serializers.Serializer):
    therapy = serializers.PrimaryKeyRelatedField(queryset=TherapyOption.objects.all())
    requested_therapies = serializers.PrimaryKeyRelatedField(
        queryset=TherapyOption.objects.all(), many=True, required=False, allow_empty=True
    )
    family_member = serializers.PrimaryKeyRelatedField(
        queryset=CustomerFamilyMember.objects.all(), required=False, allow_null=True
    )
    selected_package = serializers.PrimaryKeyRelatedField(
        queryset=TherapyPackage.objects.all(), required=False, allow_null=True
    )
    selected_offer = serializers.PrimaryKeyRelatedField(
        queryset=CommercialOffer.objects.all(), required=False, allow_null=True
    )
    preferred_date = serializers.DateField()
    preferred_time = serializers.TimeField()
    pain_area = serializers.CharField(max_length=160, required=False, allow_blank=True)
    service_address = BookingServiceAddressSerializer(required=False)
    save_as_primary_address = serializers.BooleanField(required=False, default=False)

    def validate(self, attrs):
        request = self.context["request"]
        organization = request.organization
        profile = PatientProfile.objects.filter(
            organization=organization, user=request.user, is_active=True
        ).select_related("clinic").prefetch_related("addresses").first()
        if profile is None:
            raise serializers.ValidationError(
                {"detail": "Complete customer registration before booking."}
            )
        address = next(
            (
                value
                for value in profile.addresses.all()
                if value.is_active and value.is_primary
            ),
            None,
        )
        if address is None:
            raise serializers.ValidationError(
                {"detail": "Add a primary service address before booking."}
            )
        therapy = attrs["therapy"]
        requested = list(dict.fromkeys(attrs.get("requested_therapies", [])))
        if (
            therapy.organization_id != organization.id
            or not therapy.is_active
            or not therapy.is_publicly_visible
            or therapy.is_offer_free_addon
        ):
            raise serializers.ValidationError({"therapy": "The selected therapy is unavailable."})
        requested = [value for value in requested if value.id != therapy.id]
        if len(requested) > 7 or any(
            value.organization_id != organization.id
            or not value.is_active
            or not value.is_publicly_visible
            or value.is_offer_free_addon
            for value in requested
        ):
            raise serializers.ValidationError(
                {"requested_therapies": "Select up to eight available bookable therapies in this organization."}
            )
        attrs["requested_therapies"] = requested
        family = attrs.get("family_member")
        if family and (
            family.organization_id != organization.id
            or family.customer_id != request.user.id
            or not family.is_active
        ):
            raise serializers.ValidationError(
                {"family_member": "The selected family member is unavailable."}
            )
        zone = ZoneInfo(profile.clinic.timezone or organization.timezone or "Asia/Kolkata")
        start = datetime.combine(attrs["preferred_date"], attrs["preferred_time"], zone)
        try:
            quote = calculate_quote(
                organization=organization,
                therapy_ids=[therapy.id, *[value.id for value in requested]],
                package_id=getattr(attrs.get("selected_package"), "id", None),
                offer_id=getattr(attrs.get("selected_offer"), "id", None),
                family_member=family,
                at=start,
            )
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
        if attrs["preferred_time"].minute % 15:
            raise serializers.ValidationError(
                {"preferred_time": "Select an available 15-minute time slot."}
            )
        try:
            validate_schedule(
                clinic=profile.clinic,
                start=start,
                duration_minutes=quote.duration_minutes,
            )
        except DjangoValidationError as error:
            if "operating hours have not been configured" in " ".join(error.messages).lower():
                raise serializers.ValidationError({
                    "detail": "Online booking is temporarily unavailable because service hours have not been configured. Please contact JeevaSetu."
                }) from error
            raise serializers.ValidationError({"preferred_time": error.messages}) from error
        slots = discover_slots(
            clinic=profile.clinic,
            therapy=therapy,
            date_from=attrs["preferred_date"],
            date_to=attrs["preferred_date"],
            duration_minutes=quote.duration_minutes,
        )
        requested_time = attrs["preferred_time"].replace(second=0, microsecond=0)
        if not any(
            value["scheduled_start"].astimezone(zone).time().replace(tzinfo=None) == requested_time
            for value in slots
        ):
            raise serializers.ValidationError({
                "preferred_time": "The selected appointment slot is no longer available."
            })
        attrs["_profile"] = profile
        address_data = attrs.get("service_address") or {
            field: getattr(address, field)
            for field in (
                "address_line_1", "address_line_2", "landmark", "city", "region", "pin_code",
                "latitude", "longitude", "location_accuracy_meters", "location_source",
            )
        }
        attrs["_address"] = address
        attrs["_address_data"] = address_data
        attrs["_quote"] = quote
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        profile = validated_data.pop("_profile")
        address = validated_data.pop("_address")
        address_data = validated_data.pop("_address_data")
        save_as_primary = validated_data.pop("save_as_primary_address", False)
        has_service_override = validated_data.pop("service_address", None) is not None
        quote = validated_data.pop("_quote")
        requested = validated_data.pop("requested_therapies", [])
        family = validated_data.get("family_member")
        package = validated_data.get("selected_package")
        user_mobile = "".join(character for character in (request.user.mobile_number or "") if character.isdigit())[-10:]
        if family:
            patient_name, age, gender = family.full_name, family.age, family.gender
        else:
            patient_name, gender = profile.full_name, profile.gender
            age = profile.age
            if profile.date_of_birth:
                today = timezone.localdate()
                age = today.year - profile.date_of_birth.year - (
                    (today.month, today.day)
                    < (profile.date_of_birth.month, profile.date_of_birth.day)
                )
        value = AppointmentRequest(
            organization=request.organization,
            creator=request.user,
            patient_profile=profile,
            booking_source=AppointmentRequest.BookingSource.ONLINE,
            therapy=validated_data["therapy"],
            family_member=family,
            selected_package=package,
            selected_offer_id=quote.offer_id,
            patient_name=patient_name,
            age=age,
            gender=gender,
            mobile_number=user_mobile,
            alternate_mobile="",
            email=request.user.email,
            session_preference=(
                AppointmentRequest.SessionPreference.PACKAGE
                if package
                else AppointmentRequest.SessionPreference.SINGLE
            ),
            preferred_date=validated_data["preferred_date"],
            preferred_time=validated_data["preferred_time"],
            problem_description="",
            pain_area=validated_data.get("pain_area", "").strip(),
            problem_duration="",
            doctor_reference="",
            address=" ".join(
                part for part in (address_data["address_line_1"], address_data.get("address_line_2", "")) if part
            ),
            city=address_data["city"],
            region=address_data["region"],
            pin_code=address_data["pin_code"],
            landmark=address_data.get("landmark", ""),
            google_map_link="",
            latitude=address_data.get("latitude"),
            longitude=address_data.get("longitude"),
            location_accuracy_meters=address_data.get("location_accuracy_meters"),
            location_source=address_data.get("location_source", PatientAddress.LocationSource.MANUAL),
            commercial_snapshot=quote.snapshot(),
            regular_amount=quote.regular_amount,
            discount_amount=quote.discount_amount,
            final_amount=quote.final_amount,
        )
        try:
            value.full_clean(exclude=("duplicate_fingerprint",))
            value.save()
            free_ids = [benefit["therapy_id"] for benefit in quote.free_benefits]
            additional = [*requested, *TherapyOption.objects.filter(id__in=free_ids).exclude(id=value.therapy_id)]
            value.requested_therapies.set(list(dict.fromkeys(additional)))
            if save_as_primary and has_service_override:
                for field, field_value in address_data.items():
                    setattr(address, field, field_value)
                address.full_clean()
                address.save()
            AppointmentRequestAuditEvent.objects.create(
                appointment_request=value,
                organization=request.organization,
                actor=request.user,
                event=AppointmentRequestAuditEvent.Event.SUBMITTED,
                previous_status="",
                new_status=value.status,
            )
        except IntegrityError as error:
            raise serializers.ValidationError(
                {"detail": "An identical pending appointment request already exists."}
            ) from error
        return value

    def to_representation(self, instance):
        return AppointmentRequestSerializer(instance, context=self.context).data


class OfflineAppointmentCreateSerializer(serializers.Serializer):
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    patient_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    age = serializers.IntegerField(min_value=1, max_value=120, required=False)
    gender = serializers.ChoiceField(choices=PatientProfile.Gender.choices, required=False)
    clinic = serializers.PrimaryKeyRelatedField(queryset=Clinic.objects.all())
    therapies = serializers.PrimaryKeyRelatedField(
        queryset=TherapyOption.objects.all(), many=True, allow_empty=False
    )
    physiotherapist = serializers.PrimaryKeyRelatedField(queryset=StaffProfile.objects.all())
    preferred_date = serializers.DateField()
    preferred_time = serializers.TimeField()
    service_address = BookingServiceAddressSerializer(required=False)
    booking_source = serializers.ChoiceField(
        choices=[
            choice for choice in AppointmentRequest.BookingSource.choices
            if choice[0] != AppointmentRequest.BookingSource.ONLINE
        ]
    )
    operational_note = serializers.CharField(max_length=500, required=False, allow_blank=True)
    payment_status = serializers.ChoiceField(
        choices=AppointmentPayment.Status.choices,
        default=AppointmentPayment.Status.PENDING,
    )
    payment_reference = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate(self, attrs):
        request = self.context["request"]
        organization = request.organization
        clinic = attrs["clinic"]
        if clinic.organization_id != organization.id or not clinic.is_active:
            raise serializers.ValidationError({"clinic": "The selected clinic is unavailable."})
        level, clinic_ids = actor_role_scope(request.user, organization)
        if level == Role.MANAGER and clinic.id not in (clinic_ids or ()):
            raise serializers.ValidationError({"clinic": "The selected clinic is unavailable."})
        patient = PatientProfile.objects.filter(
            organization=organization,
            mobile_number=attrs["mobile_number"],
            is_active=True,
        ).select_related("clinic").prefetch_related("addresses").first()
        if patient and patient.clinic_id != clinic.id:
            raise serializers.ValidationError(
                {"clinic": "This mobile number belongs to a patient at another clinic."}
            )
        if patient is None:
            missing = [
                field for field in ("patient_name", "age", "gender", "service_address")
                if not attrs.get(field)
            ]
            if missing:
                raise serializers.ValidationError(
                    {field: "This field is required for a new patient." for field in missing}
                )
        else:
            attrs["_patient"] = patient
        therapies = list(dict.fromkeys(attrs["therapies"]))
        if len(therapies) > 8 or any(
            therapy.organization_id != organization.id
            or not therapy.is_active
            or therapy.is_offer_free_addon
            for therapy in therapies
        ):
            raise serializers.ValidationError(
                {"therapies": "Select up to eight active bookable therapies."}
            )
        attrs["therapies"] = therapies
        physiotherapist = attrs["physiotherapist"]
        if (
            physiotherapist.organization_id != organization.id
            or physiotherapist.clinic_id != clinic.id
            or physiotherapist.staff_type != Role.PHYSIOTHERAPIST
        ):
            raise serializers.ValidationError(
                {"physiotherapist": "The selected Physiotherapist is unavailable."}
            )
        zone = ZoneInfo(clinic.timezone or organization.timezone or "Asia/Kolkata")
        start = datetime.combine(attrs["preferred_date"], attrs["preferred_time"], zone)
        try:
            quote = calculate_quote(
                organization=organization,
                therapy_ids=[therapy.id for therapy in therapies],
                at=start,
            )
            validate_schedule(clinic=clinic, start=start, duration_minutes=quote.duration_minutes)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.messages) from error
        address = attrs.get("service_address")
        if address is None and patient is not None:
            primary = next(
                (item for item in patient.addresses.all() if item.is_active and item.is_primary),
                None,
            )
            if primary is None:
                raise serializers.ValidationError(
                    {"service_address": "This patient does not have a confirmed primary address."}
                )
            address = {
                field: getattr(primary, field)
                for field in (
                    "address_line_1", "address_line_2", "landmark", "city", "region",
                    "pin_code", "latitude", "longitude", "location_accuracy_meters",
                    "location_source",
                )
            }
        attrs["_address"] = address
        attrs["_quote"] = quote
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context["request"]
        organization = request.organization
        patient = validated_data.pop("_patient", None)
        address = validated_data.pop("_address")
        quote = validated_data.pop("_quote")
        therapies = validated_data.pop("therapies")
        clinic = validated_data.pop("clinic")
        physiotherapist = validated_data.pop("physiotherapist")
        operational_note = validated_data.pop("operational_note", "").strip()
        payment_status = validated_data.pop("payment_status")
        payment_reference = validated_data.pop("payment_reference", "").strip()
        try:
            if patient is None:
                patient = PatientProfile(
                    organization=organization,
                    clinic=clinic,
                    full_name=validated_data.get("patient_name", "").strip(),
                    mobile_number=validated_data["mobile_number"],
                    gender=validated_data["gender"],
                    age=validated_data["age"],
                    emergency_contact_name=validated_data.get("patient_name", "").strip(),
                    emergency_contact_relationship="Self",
                    emergency_contact_mobile=validated_data["mobile_number"],
                )
                patient.save()
                primary = PatientAddress(patient=patient, label="Home", is_primary=True, **address)
                primary.full_clean()
                primary.save()
            age = patient.age
            if patient.date_of_birth:
                today = timezone.localdate()
                age = today.year - patient.date_of_birth.year - (
                    (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day)
                )
            source = AppointmentRequest(
                organization=organization,
                creator=patient.user,
                patient_profile=patient,
                therapy=therapies[0],
                patient_name=patient.full_name,
                age=age,
                gender=patient.gender,
                mobile_number=patient.mobile_number,
                session_preference=AppointmentRequest.SessionPreference.SINGLE,
                preferred_date=validated_data["preferred_date"],
                preferred_time=validated_data["preferred_time"],
                address=" ".join(
                    part for part in (address["address_line_1"], address.get("address_line_2", "")) if part
                ),
                city=address["city"],
                region=address["region"],
                pin_code=address["pin_code"],
                landmark=address.get("landmark", ""),
                latitude=address.get("latitude"),
                longitude=address.get("longitude"),
                location_accuracy_meters=address.get("location_accuracy_meters"),
                location_source=address.get("location_source", PatientAddress.LocationSource.MANUAL),
                booking_source=validated_data["booking_source"],
                owner_remarks=operational_note,
                commercial_snapshot=quote.snapshot(),
                regular_amount=quote.regular_amount,
                discount_amount=quote.discount_amount,
                final_amount=quote.final_amount,
            )
            source.full_clean(exclude=("duplicate_fingerprint",))
            source.save()
            source.requested_therapies.set(therapies[1:])
            AppointmentRequestAuditEvent.objects.create(
                appointment_request=source,
                organization=organization,
                actor=request.user,
                event=AppointmentRequestAuditEvent.Event.SUBMITTED,
                previous_status="",
                new_status=source.status,
                internal_note=f"Offline booking source: {source.get_booking_source_display()}",
            )
            from apps.appointments.scheduling import decide_appointment_request
            source, appointment = decide_appointment_request(
                source,
                actor=request.user,
                action="ACCEPT_ASSIGN",
                physiotherapist=physiotherapist,
            )
            appointment.operational_notes = operational_note
            appointment.save(update_fields=("operational_notes", "updated_at"))
            payment = AppointmentPayment.objects.create(
                appointment=appointment,
                organization=organization,
                amount_due=source.final_amount,
                status=payment_status,
                paid_at=timezone.now() if payment_status == AppointmentPayment.Status.PAID else None,
                reference=payment_reference,
                note=f"Created with {source.get_booking_source_display().lower()} booking.",
                updated_by=request.user,
            )
        except (DjangoValidationError, IntegrityError) as error:
            raise serializers.ValidationError(str(error)) from error
        return appointment, patient, payment


class ReviewOperationsSerializer(serializers.ModelSerializer):
    customer_display_name = serializers.SerializerMethodField()
    physiotherapist_name = serializers.CharField(source="physiotherapist.user.get_full_name", read_only=True)
    appointment_date = serializers.DateTimeField(source="appointment.scheduled_start", read_only=True)
    therapy_name = serializers.CharField(source="appointment.therapy.name", read_only=True)

    class Meta:
        model = AppointmentRating
        fields = ("id", "stars", "comment", "moderation_status", "moderation_reason", "customer_display_name", "physiotherapist_name", "appointment_date", "therapy_name", "created_at")

    def get_customer_display_name(self, value):
        return value.customer.first_name or "Customer"


class ReviewModerationSerializer(serializers.Serializer):
    moderation_status = serializers.ChoiceField(choices=(AppointmentRating.ModerationStatus.APPROVED, AppointmentRating.ModerationStatus.HIDDEN))
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, trim_whitespace=True)

    def validate(self, attrs):
        if attrs["moderation_status"] == AppointmentRating.ModerationStatus.HIDDEN and len(attrs.get("reason", "")) < 3:
            raise serializers.ValidationError({"reason": "A moderation reason is required when hiding a review."})
        return attrs


class PublicReviewSerializer(serializers.ModelSerializer):
    customer_display_name = serializers.SerializerMethodField()
    physiotherapist_name = serializers.CharField(source="physiotherapist.user.get_full_name", read_only=True)

    class Meta:
        model = AppointmentRating
        fields = ("stars", "comment", "customer_display_name", "physiotherapist_name", "created_at")

    def get_customer_display_name(self, value):
        return value.customer.first_name or "Customer"


class PractitionerPaymentSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="appointment.therapy.name", read_only=True)
    service_date = serializers.DateTimeField(source="appointment.scheduled_start", read_only=True)

    class Meta:
        model = PractitionerPayment
        fields = ("id", "appointment", "therapy_name", "service_date", "payable_amount", "status", "paid_at", "reference", "note", "updated_at")
        read_only_fields = ("id", "appointment", "therapy_name", "service_date", "paid_at", "updated_at")


class AppointmentPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppointmentPayment
        fields = ("id", "appointment", "amount_due", "status", "paid_at", "reference", "note", "updated_at")
        read_only_fields = ("id", "appointment", "amount_due", "paid_at", "updated_at")

    def validate_status(self, value):
        if self.instance and self.instance.status == AppointmentPayment.Status.PAID and value != AppointmentPayment.Status.PAID:
            raise serializers.ValidationError("A recorded payment cannot be returned to pending.")
        return value
