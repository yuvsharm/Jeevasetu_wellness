import csv
import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Q
from django.http import FileResponse, HttpResponse
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Role, RoleAssignment
from apps.accounts.permissions import (
    IsCustomer,
    IsEnabledAuthenticated,
    IsOwner,
    IsOwnerOrManager,
    IsPhysiotherapist,
    active_roles,
)
from apps.accounts.role_policy import actor_role_scope
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentChangeRequest,
    AppointmentPayment,
    AppointmentRequest,
    AppointmentRating,
    AppointmentRatingModerationEvent,
    CommercialOffer,
    CommercialAuditEvent,
    PractitionerPayment,
    TherapyOption,
    TherapyPackage,
)
from apps.appointments.scheduling import (
    assign_physiotherapist,
    cancel_appointment,
    complete_and_confirm_payment,
    provision_prepaid_appointment,
    record_rejected_lifecycle_action,
    reschedule_appointment,
    rebook_closed_appointment,
    respond_to_assignment,
    transition_status,
    submit_customer_payment,
    update_journey,
    unassign_physiotherapist,
    validate_schedule,
    verify_customer_payment,
    decide_appointment_request,
    ensure_request_practitioner_eligible,
)
from apps.appointments.serializers import (
    AppointmentAuditSerializer,
    AppointmentCancellationSerializer,
    AppointmentChangeRequestSerializer,
    AppointmentCompletionPaymentSerializer,
    AppointmentPaymentSerializer,
    AppointmentDetailSerializer,
    AppointmentListSerializer,
    AppointmentRequestSerializer,
    AppointmentRequestDecisionSerializer,
    AuthenticatedAppointmentRequestSerializer,
    CustomerRebookSerializer,
    OwnerAppointmentRebookSerializer,
    AppointmentRatingSerializer,
    PublicReviewSerializer,
    ReviewModerationSerializer,
    ReviewOperationsSerializer,
    PractitionerPaymentSerializer,
    AppointmentRescheduleSerializer,
    AppointmentStatusSerializer,
    JourneyUpdateSerializer,
    AppointmentWriteSerializer,
    AssignmentResponseSerializer,
    AssignmentSerializer,
    AvailabilityQuerySerializer,
    BookingOtpRequestSerializer,
    BookingOtpVerifySerializer,
    CommercialOfferSerializer,
    CommercialQuoteSerializer,
    CancelAppointmentSerializer,
    CustomerAppointmentSerializer,
    CustomerAppointmentRequestSerializer,
    OwnerAppointmentUpdateSerializer,
    OfflineAppointmentCreateSerializer,
    PhysiotherapistAppointmentSerializer,
    PhysiotherapistWorkloadSerializer,
    TherapyOptionSerializer,
    TherapyCommercialSerializer,
    TherapyPackageSerializer,
    UnassignmentSerializer,
)
from apps.appointments.booking_verification import (
    issue_booking_otp_details,
    verify_booking_otp,
)


def commercial_audit_payload(data):
    """Convert serializer return values (including UUIDs) to JSON-safe primitives."""
    return json.loads(json.dumps(data, cls=DjangoJSONEncoder))
from apps.appointments.commercial import calculate_quote
from apps.appointments.analytics import build_owner_analytics, resolve_range
from apps.patients.models import CustomerFamilyMember, PatientProfile
from apps.availability.services import ensure_physiotherapist_available
from apps.staff.models import StaffProfile


class HasTenant:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request, "organization", None) is None:
            raise NotFound("Organization context is unavailable.")


class OwnerAnalyticsView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwner)

    def get(self, request):
        try:
            scope = resolve_range(request.query_params)
        except ValueError as error:
            raise ValidationError({"date_range": str(error)}) from error
        return Response(build_owner_analytics(request.organization, scope))


class OwnerAnalyticsCsvView(OwnerAnalyticsView):
    def get(self, request):
        try:
            scope = resolve_range(request.query_params)
        except ValueError as error:
            raise ValidationError({"date_range": str(error)}) from error
        data = build_owner_analytics(request.organization, scope)
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="owner-business-summary-{data["scope"]["start_date"]}-to-{data["scope"]["end_date"]}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(("NuriPain Ease Owner Business Summary", request.organization.display_name))
        writer.writerow(("Date scope", data["scope"]["start_date"], data["scope"]["end_date"], data["scope"]["timezone"]))
        writer.writerow(())
        writer.writerow(("KPI", "Value"))
        for key, value in data["kpis"].items():
            writer.writerow((key.replace("_", " ").title(), value if value is not None else "Unavailable"))
        writer.writerow(())
        writer.writerow(("Therapy", "Bookings", "Completed", "Booked value", "Approved average rating"))
        for row in data["therapies"]:
            writer.writerow((row["name"], row["bookings"], row["completed"], row["booked_value"], row["average_rating"] or ""))
        writer.writerow(())
        writer.writerow(("Commercial benefit", "Type", "Bookings", "Booked value", "Discounts", "Completion rate"))
        for row in data["commercial_performance"]:
            writer.writerow((row["name"], row["kind"], row["bookings"], row["booked_value"], row["discounts"], row["completion_rate"]))
        writer.writerow(())
        writer.writerow(("Attention item", "Count"))
        for key, value in data["attention"].items():
            writer.writerow((key.replace("_", " ").title(), value))
        return response


class TherapyListView(HasTenant, generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = TherapyOptionSerializer

    def get_queryset(self):
        return TherapyOption.objects.filter(organization=self.request.organization, is_active=True, is_publicly_visible=True)


class PublicCommercialCatalogView(HasTenant, GenericAPIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        now = timezone.now()
        packages = TherapyPackage.objects.filter(organization=request.organization, is_active=True, is_publicly_visible=True).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now)).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now)).select_related("therapy")
        offers = CommercialOffer.objects.filter(organization=request.organization, is_active=True, is_publicly_visible=True).filter(Q(valid_from__isnull=True) | Q(valid_from__lte=now)).filter(Q(valid_until__isnull=True) | Q(valid_until__gt=now)).prefetch_related("eligible_therapies").select_related("free_therapy")
        therapies = TherapyOption.objects.filter(organization=request.organization, is_active=True, is_publicly_visible=True)
        return Response({"therapies": TherapyCommercialSerializer(therapies, many=True).data, "packages": TherapyPackageSerializer(packages, many=True).data, "offers": CommercialOfferSerializer(offers, many=True).data})


class CommercialQuoteView(HasTenant, GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = CommercialQuoteSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        family = None
        family_id = serializer.validated_data.get("family_member_id")
        if family_id:
            if not request.user.is_authenticated:
                raise PermissionDenied("Sign in to use a family offer.")
            family = CustomerFamilyMember.objects.filter(id=family_id, organization=request.organization, customer=request.user, is_active=True).first()
            if not family:
                raise PermissionDenied("The selected family member is unavailable.")
        try:
            quote = calculate_quote(
                organization=request.organization,
                therapy_ids=serializer.validated_data["therapy_ids"],
                package_id=serializer.validated_data.get("package_id"),
                offer_id=serializer.validated_data.get("offer_id"),
                family_member=family,
                at=serializer.validated_data.get("service_at"),
            )
        except DjangoValidationError as error:
            raise ValidationError(error.message_dict) from error
        return Response(quote.snapshot())


class TherapyManagementListCreateView(HasTenant, generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = TherapyCommercialSerializer

    def get_queryset(self):
        return TherapyOption.objects.filter(organization=self.request.organization)

    def perform_create(self, serializer):
        value = serializer.save(organization=self.request.organization, default_duration_minutes=45)
        CommercialAuditEvent.objects.create(organization=self.request.organization, actor=self.request.user, object_kind="THERAPY", object_id=value.id, action="CREATED", after=commercial_audit_payload(serializer.data))


class TherapyManagementDetailView(HasTenant, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = TherapyCommercialSerializer

    def get_queryset(self):
        return TherapyOption.objects.filter(organization=self.request.organization)

    def perform_update(self, serializer):
        before = TherapyCommercialSerializer(self.get_object()).data
        value = serializer.save()
        CommercialAuditEvent.objects.create(organization=self.request.organization, actor=self.request.user, object_kind="THERAPY", object_id=value.id, action="UPDATED", before=commercial_audit_payload(before), after=commercial_audit_payload(serializer.data))

    def perform_destroy(self, instance):
        references = instance.protected_reference_summary()
        if any(references.values()):
            raise ValidationError({
                "detail": "This therapy has protected history and cannot be deleted. Deactivate it instead.",
                "protected_references": references,
            })
        before = TherapyCommercialSerializer(instance).data
        object_id = instance.id
        instance.delete()
        CommercialAuditEvent.objects.create(
            organization=self.request.organization,
            actor=self.request.user,
            object_kind="THERAPY",
            object_id=object_id,
            action="DELETED",
            before=commercial_audit_payload(before),
        )


class PackageManagementListCreateView(HasTenant, generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = TherapyPackageSerializer

    def get_queryset(self):
        return TherapyPackage.objects.filter(organization=self.request.organization).select_related("therapy")

    def perform_create(self, serializer):
        value = serializer.save(organization=self.request.organization)
        CommercialAuditEvent.objects.create(organization=self.request.organization, actor=self.request.user, object_kind="PACKAGE", object_id=value.id, action="CREATED", after=commercial_audit_payload(serializer.data))


class PackageManagementDetailView(PackageManagementListCreateView, generics.RetrieveUpdateAPIView):
    def perform_update(self, serializer):
        before = TherapyPackageSerializer(self.get_object()).data
        value = serializer.save()
        CommercialAuditEvent.objects.create(organization=self.request.organization, actor=self.request.user, object_kind="PACKAGE", object_id=value.id, action="UPDATED", before=commercial_audit_payload(before), after=commercial_audit_payload(serializer.data))


class OfferManagementListCreateView(HasTenant, generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = CommercialOfferSerializer

    def get_queryset(self):
        return CommercialOffer.objects.filter(organization=self.request.organization).prefetch_related("eligible_therapies").select_related("free_therapy")

    def perform_create(self, serializer):
        value = serializer.save(organization=self.request.organization)
        CommercialAuditEvent.objects.create(organization=self.request.organization, actor=self.request.user, object_kind="OFFER", object_id=value.id, action="CREATED", after=commercial_audit_payload(serializer.data))


class OfferManagementDetailView(OfferManagementListCreateView, generics.RetrieveUpdateDestroyAPIView):
    def perform_update(self, serializer):
        before = CommercialOfferSerializer(self.get_object()).data
        value = serializer.save()
        CommercialAuditEvent.objects.create(organization=self.request.organization, actor=self.request.user, object_kind="OFFER", object_id=value.id, action="UPDATED", before=commercial_audit_payload(before), after=commercial_audit_payload(serializer.data))

    def perform_destroy(self, instance):
        references = instance.protected_reference_summary()
        if any(references.values()):
            raise ValidationError({
                "detail": "This offer has historical booking records and cannot be permanently deleted. Archive it instead.",
                "protected_references": references,
            })
        before = CommercialOfferSerializer(instance).data
        object_id = instance.id
        instance.delete()
        CommercialAuditEvent.objects.create(
            organization=self.request.organization,
            actor=self.request.user,
            object_kind="OFFER",
            object_id=object_id,
            action="DELETED",
            before=commercial_audit_payload(before),
        )


class AppointmentCreateView(HasTenant, generics.CreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AuthenticatedAppointmentRequestSerializer

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = serializer.save()
        provision_prepaid_appointment(value, actor=request.user)
        return Response(
            CustomerAppointmentRequestSerializer(value, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class QuickAppointmentCreateView(AppointmentCreateView):
    """Compatibility alias for the authenticated customer booking endpoint."""


class BookingOtpIssueView(HasTenant, generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = BookingOtpRequestSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        mobile_number = serializer.validated_data["mobile_number"]
        try:
            verification, delivery = issue_booking_otp_details(
                organization=request.organization,
                mobile_number=mobile_number,
                client_key=request.META.get("REMOTE_ADDR", "anonymous-client"),
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        payload = {
            "verification_id": str(verification.id),
            "mobile_number": mobile_number,
            "expires_at": verification.expires_at.isoformat(),
            "message": "Use the OTP sent to your mobile number to continue.",
        }
        if not settings.MSG91_ENABLED and (getattr(settings, "DEBUG", False) or "DevBookingOtpDelivery" in getattr(settings, "BOOKING_OTP_DELIVERY_BACKEND", "")):
            payload["otp"] = delivery.otp
        return Response(payload, status=status.HTTP_201_CREATED)


class BookingOtpVerifyView(HasTenant, generics.GenericAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = BookingOtpVerifySerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = verify_booking_otp(
                organization=request.organization,
                verification_id=serializer.validated_data["verification_id"],
                mobile_number=serializer.validated_data["mobile_number"],
                otp=serializer.validated_data.get("otp"),
                access_token=serializer.validated_data.get("access_token"),
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response({"token": token}, status=status.HTTP_200_OK)


class CustomerAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerAppointmentRequestSerializer

    def get_queryset(self):
        return AppointmentRequest.objects.filter(
            organization=self.request.organization, creator=self.request.user
        ).select_related(
            "therapy", "family_member", "patient_profile", "creator",
            "operational_appointment__physiotherapist__user",
            "operational_appointment__physiotherapist__practitioner_profile",
            "operational_appointment__payment", "operational_appointment__rating",
        ).prefetch_related(
            "requested_therapies", "audit_events",
            "operational_appointment__physiotherapist__therapy_competencies",
            "operational_appointment__physiotherapist__specializations",
        )


class CustomerAppointmentDetailView(HasTenant, generics.RetrieveAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerAppointmentRequestSerializer

    def get_queryset(self):
        return AppointmentRequest.objects.filter(
            organization=self.request.organization, creator=self.request.user
        ).select_related(
            "therapy", "family_member", "patient_profile", "creator",
            "operational_appointment__physiotherapist__user",
            "operational_appointment__physiotherapist__practitioner_profile",
            "operational_appointment__payment", "operational_appointment__rating",
        ).prefetch_related(
            "requested_therapies", "audit_events",
            "operational_appointment__physiotherapist__therapy_competencies",
            "operational_appointment__physiotherapist__specializations",
        )

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())
        value = queryset.filter(
            Q(pk=self.kwargs["pk"]) | Q(operational_appointment__pk=self.kwargs["pk"])
        ).first()
        if value is None:
            raise NotFound("Appointment is unavailable.")
        self.check_object_permissions(self.request, value)
        return value


class CustomerPaymentSubmissionView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)

    def post(self, request, pk):
        if request.data.get("acknowledged") is not True:
            raise ValidationError("Accept the prepaid booking terms before submitting payment.")
        appointment = Appointment.objects.filter(
            pk=pk,
            organization=request.organization,
            originating_request__creator=request.user,
        ).select_related("originating_request", "payment").first()
        if appointment is None:
            raise NotFound("Payment is unavailable.")
        try:
            appointment = submit_customer_payment(appointment, actor=request.user)
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(CustomerAppointmentSerializer(appointment, context={"request": request}).data)


class CustomerAppointmentCancelView(CustomerAppointmentDetailView, generics.UpdateAPIView):
    serializer_class = CancelAppointmentSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data={})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(CustomerAppointmentRequestSerializer(instance, context={"request": request}).data)


class CustomerAppointmentRebookView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerRebookSerializer

    @transaction.atomic
    def post(self, request, pk):
        appointment = Appointment.objects.select_related("originating_request", "patient", "clinic").filter(
            pk=pk, organization=request.organization,
            originating_request__creator=request.user,
            status=Appointment.Status.COMPLETED,
        ).first()
        if not appointment or not appointment.originating_request_id:
            raise NotFound("This completed appointment is unavailable for rebooking.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        source = appointment.originating_request
        snapshot_therapy_ids = source.commercial_snapshot.get("therapy_ids", [])
        therapy_ids = list(dict.fromkeys(
            [str(value) for value in snapshot_therapy_ids]
            or [
                str(source.therapy_id),
                *[
                    str(value)
                    for value in source.requested_therapies.filter(
                        is_offer_free_addon=False
                    ).values_list("id", flat=True)
                ],
            ]
        ))
        therapies_by_id = {
            str(value.id): value
            for value in TherapyOption.objects.filter(id__in=therapy_ids)
        }
        requested = [
            therapies_by_id[value]
            for value in therapy_ids
            if value != str(source.therapy_id) and value in therapies_by_id
        ]
        start = datetime.combine(
            serializer.validated_data["preferred_date"],
            serializer.validated_data["preferred_time"],
            ZoneInfo(appointment.clinic.timezone or request.organization.timezone or "Asia/Kolkata"),
        )
        quote = calculate_quote(
            organization=request.organization,
            therapy_ids=therapy_ids,
            family_member=source.family_member,
            at=start,
        )
        validate_schedule(
            clinic=appointment.clinic,
            start=start,
            duration_minutes=quote.duration_minutes,
        )
        primary = appointment.patient.addresses.filter(is_primary=True, is_active=True).first()
        if primary is None:
            raise ValidationError("Confirm a primary service address before booking again.")
        value = AppointmentRequest.objects.create(
            organization=request.organization, creator=request.user,
            family_member=source.family_member, therapy=source.therapy,
            selected_offer_id=quote.offer_id, selected_package_id=quote.package_id,
            commercial_snapshot=quote.snapshot(), regular_amount=quote.regular_amount,
            discount_amount=quote.discount_amount, final_amount=quote.final_amount,
            preferred_practitioner=None, patient_name=source.patient_name, age=source.age,
            gender=source.gender, mobile_number=source.mobile_number,
            alternate_mobile=source.alternate_mobile, email=source.email,
            session_preference=AppointmentRequest.SessionPreference.SINGLE,
            preferred_date=serializer.validated_data["preferred_date"],
            preferred_time=serializer.validated_data["preferred_time"],
            problem_description=source.problem_description, pain_area=source.pain_area,
            problem_duration=source.problem_duration, doctor_reference=source.doctor_reference,
            address=", ".join(filter(None, (primary.address_line_1, primary.address_line_2))),
            city=primary.city, region=primary.region, pin_code=primary.pin_code,
            landmark=primary.landmark, google_map_link="",
            latitude=primary.latitude, longitude=primary.longitude,
            location_accuracy_meters=primary.location_accuracy_meters,
            location_source=primary.location_source,
        )
        value.requested_therapies.set(requested)
        from apps.appointments.notification_events import notify_booking_request

        notify_booking_request(value)
        return Response(AppointmentRequestSerializer(value, context={"request": request}).data, status=status.HTTP_201_CREATED)


class OwnerRequestPagination(PageNumberPagination):
    page_size = 8
    page_size_query_param = "page_size"
    max_page_size = 8


class OwnerAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = CustomerAppointmentRequestSerializer
    pagination_class = OwnerRequestPagination

    def get_queryset(self):
        level, _ = actor_role_scope(self.request.user, self.request.organization)
        if level not in (Role.OWNER, Role.MANAGER):
            raise PermissionDenied("Operations access is required.")
        queryset = AppointmentRequest.objects.filter(
            organization=self.request.organization
        ).select_related(
            "therapy", "creator", "patient_profile", "family_member",
            "operational_appointment__physiotherapist__user",
            "operational_appointment__physiotherapist__practitioner_profile",
            "operational_appointment__payment",
        ).prefetch_related(
            "requested_therapies", "audit_events",
            "operational_appointment__physiotherapist__therapy_competencies",
            "operational_appointment__physiotherapist__specializations",
        )
        if level == Role.MANAGER:
            _, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
            queryset = queryset.filter(
                Q(patient_profile__clinic_id__in=clinic_ids or ())
                | Q(creator__patient_profiles__clinic_id__in=clinic_ids or ())
                | Q(creator=self.request.user)
            ).distinct()
        status_value = self.request.query_params.get("status", "")
        search = self.request.query_params.get("search", "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        if search:
            queryset = queryset.filter(
                Q(patient_name__icontains=search)
                | Q(mobile_number__icontains=search)
                | Q(therapy__name__icontains=search)
                | Q(status__icontains=search)
            )
        return queryset


class OfflineAppointmentCreateView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = OfflineAppointmentCreateSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        existing = PatientProfile.objects.filter(
            organization=request.organization,
            mobile_number=serializer.validated_data["mobile_number"],
            is_active=True,
        ).exists()
        appointment, patient, payment = serializer.save()
        result = AppointmentDetailSerializer(appointment, context={"request": request}).data
        result.update({
            "patient_reused": existing,
            "patient_id": str(patient.id),
            "booking_source": appointment.originating_request.booking_source,
            "payment_status": payment.status,
            "payment_amount_due": str(payment.amount_due),
        })
        return Response(result, status=status.HTTP_201_CREATED)


class OwnerAppointmentDetailView(HasTenant, generics.RetrieveUpdateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = CustomerAppointmentRequestSerializer

    def get_queryset(self):
        level, _ = actor_role_scope(self.request.user, self.request.organization)
        if level not in (Role.OWNER, Role.MANAGER):
            raise PermissionDenied("Operations access is required.")
        return AppointmentRequest.objects.filter(
            organization=self.request.organization
        ).select_related(
            "therapy", "creator", "patient_profile", "family_member",
            "operational_appointment__physiotherapist__user",
            "operational_appointment__physiotherapist__practitioner_profile",
            "operational_appointment__payment",
        ).prefetch_related("requested_therapies", "audit_events")

    def get_serializer_class(self):
        return (
            OwnerAppointmentUpdateSerializer
            if self.request.method in ("PUT", "PATCH")
            else CustomerAppointmentRequestSerializer
        )


class AppointmentPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class OperationalScopeMixin(HasTenant):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)

    def scoped_queryset(self):
        queryset = Appointment.objects.filter(organization=self.request.organization)
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        if level == Role.MANAGER:
            queryset = queryset.filter(clinic_id__in=clinic_ids or ())
        return queryset.select_related(
            "clinic",
            "patient",
            "patient__user",
            "therapy",
            "physiotherapist__user",
            "originating_request",
            "assigned_by",
            "payment",
            "payment__updated_by",
        )


class OperationalAppointmentListCreateView(OperationalScopeMixin, generics.ListCreateAPIView):
    pagination_class = AppointmentPagination

    def get_serializer_class(self):
        return (
            AppointmentWriteSerializer
            if self.request.method == "POST"
            else AppointmentListSerializer
        )

    def get_queryset(self):
        queryset = self.scoped_queryset()
        for key in ("clinic", "status", "therapy", "physiotherapist", "patient"):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{key: value})
        assignment_status = self.request.query_params.get("assignment_status")
        journey_status = self.request.query_params.get("journey_status")
        payment_status = self.request.query_params.get("payment_status")
        if assignment_status:
            queryset = queryset.filter(assignment_status=assignment_status)
        if journey_status:
            queryset = queryset.filter(journey_status=journey_status)
        if payment_status:
            queryset = queryset.filter(payment__status=payment_status)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(patient__full_name__icontains=search)
                | Q(patient__patient_identifier__icontains=search)
                | Q(patient__mobile_number__icontains=search)
                | Q(originating_request__id__icontains=search)
                | Q(physiotherapist__user__first_name__icontains=search)
                | Q(physiotherapist__user__last_name__icontains=search)
                | Q(assigned_by__first_name__icontains=search)
                | Q(assigned_by__last_name__icontains=search)
                | Q(status__icontains=search)
            )
        view = self.request.query_params.get("view")
        today = timezone.localdate()
        now = timezone.now()
        attention = Q(status__in=(
            Appointment.Status.DRAFT,
            Appointment.Status.PENDING_ASSIGNMENT,
            Appointment.Status.SCHEDULED,
            Appointment.Status.CONFIRMED,
        )) & (
            Q(physiotherapist__isnull=True)
            | Q(assignment_status__in=(
                Appointment.AssignmentStatus.UNASSIGNED,
                Appointment.AssignmentStatus.REJECTED,
            ))
        )
        if view == "active":
            queryset = queryset.exclude(status__in=Appointment.FINAL_STATUSES).filter(
                Q(scheduled_end__gte=now) | Q(status=Appointment.Status.IN_PROGRESS)
            ).exclude(attention)
        elif view == "attention":
            queryset = queryset.filter(attention)
        elif view == "history":
            queryset = queryset.filter(
                Q(status__in=Appointment.FINAL_STATUSES) | Q(scheduled_end__lt=now)
            )
        elif view == "today":
            queryset = queryset.filter(scheduled_start__date=today)
        elif view == "upcoming":
            queryset = queryset.filter(scheduled_start__date__gt=today).exclude(
                status=Appointment.Status.CANCELLED
            )
        elif view == "cancelled":
            queryset = queryset.filter(status=Appointment.Status.CANCELLED)
        elif view == "pending":
            queryset = queryset.filter(status__in=(Appointment.Status.DRAFT, Appointment.Status.PENDING_ASSIGNMENT, Appointment.Status.SCHEDULED))
        elif view == "awaiting_therapist":
            queryset = queryset.filter(assignment_status__in=(Appointment.AssignmentStatus.UNASSIGNED, Appointment.AssignmentStatus.PENDING, Appointment.AssignmentStatus.REJECTED))
        elif view == "accepted":
            queryset = queryset.filter(assignment_status=Appointment.AssignmentStatus.ACCEPTED)
        elif view == "en_route":
            queryset = queryset.filter(journey_status=Appointment.JourneyStatus.EN_ROUTE)
        elif view == "started":
            queryset = queryset.filter(status=Appointment.Status.IN_PROGRESS)
        elif view == "completed":
            queryset = queryset.filter(status=Appointment.Status.COMPLETED)
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(scheduled_start__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_start__date__lte=date_to)
        ordering = self.request.query_params.get("ordering", "scheduled_start")
        if ordering not in ("scheduled_start", "-scheduled_start", "created_at", "-created_at"):
            ordering = "scheduled_start"
        return queryset.order_by(ordering)

    def perform_create(self, serializer):
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        clinic = serializer.validated_data["clinic"]
        if level == Role.MANAGER and clinic.id not in (clinic_ids or ()):
            raise PermissionDenied("The selected clinic is unavailable.")
        serializer.save()


class AppointmentCalendarView(OperationalAppointmentListCreateView):
    http_method_names = ("get", "head", "options")


class AppointmentOperationsQueueView(AppointmentCalendarView):
    def get_queryset(self):
        queryset = super().get_queryset()
        if not self.request.query_params.get("status") and self.request.query_params.get("view") not in ("completed", "cancelled"):
            queryset = queryset.filter(
                status__in=(
                    Appointment.Status.DRAFT,
                    Appointment.Status.PENDING_ASSIGNMENT,
                    Appointment.Status.SCHEDULED,
                    Appointment.Status.CONFIRMED,
                    Appointment.Status.IN_PROGRESS,
                )
            )
        return queryset


class OperationalAppointmentDetailView(OperationalScopeMixin, generics.RetrieveUpdateAPIView):
    def get_queryset(self):
        return self.scoped_queryset()

    def get_serializer_class(self):
        return (
            AppointmentWriteSerializer
            if self.request.method in ("PATCH", "PUT")
            else AppointmentDetailSerializer
        )

    def perform_update(self, serializer):
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        clinic = serializer.validated_data.get("clinic", serializer.instance.clinic)
        if level == Role.MANAGER and clinic != serializer.instance.clinic:
            raise PermissionDenied("Managers cannot transfer appointments between clinics.")
        if level == Role.MANAGER and clinic.id not in (clinic_ids or ()):
            raise PermissionDenied("The selected clinic is unavailable.")
        serializer.save()


class ConvertAppointmentRequestView(OperationalScopeMixin, GenericAPIView):
    serializer_class = AppointmentWriteSerializer

    @transaction.atomic
    def post(self, request, request_id):
        source = (
            AppointmentRequest.objects.select_for_update()
            .filter(
                pk=request_id,
                organization=request.organization,
                status=AppointmentRequest.Status.APPROVED,
            )
            .first()
        )
        if source is None:
            raise NotFound("An approved appointment request is unavailable.")
        existing = Appointment.objects.filter(originating_request=source).first()
        if existing:
            return Response(
                AppointmentDetailSerializer(existing, context={"request": request}).data,
                status=status.HTTP_200_OK,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        clinic = serializer.validated_data["clinic"]
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        if level == Role.MANAGER and clinic.id not in (clinic_ids or ()):
            raise PermissionDenied("The selected clinic is unavailable.")
        try:
            appointment = serializer.save(originating_request=source)
        except IntegrityError:
            appointment = Appointment.objects.get(originating_request=source)
        audit = appointment.audit_events.filter(event=AppointmentAuditEvent.Event.CREATED).latest(
            "created_at"
        )
        audit.event = AppointmentAuditEvent.Event.CONVERTED
        audit.save(update_fields=("event",))
        return Response(
            AppointmentDetailSerializer(appointment, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AppointmentAssignmentView(OperationalScopeMixin, GenericAPIView):
    serializer_class = AssignmentSerializer

    def post(self, request, pk):
        appointment = self.scoped_queryset().filter(pk=pk).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        physiotherapist = serializer.validated_data["physiotherapist"]
        if (
            physiotherapist.organization_id != request.organization.id
            or physiotherapist.clinic_id != appointment.clinic_id
            or physiotherapist.staff_type != Role.PHYSIOTHERAPIST
            or not RoleAssignment.objects.filter(
                user=physiotherapist.user,
                user__is_active=True,
                user__is_enabled=True,
                organization=request.organization,
                clinic=appointment.clinic,
                role=Role.PHYSIOTHERAPIST,
                is_active=True,
                organization_membership__is_active=True,
                clinic_membership__is_active=True,
            ).exists()
        ):
            raise ValidationError("The selected Physiotherapist is unavailable.")
        try:
            appointment = assign_physiotherapist(
                appointment,
                physiotherapist=physiotherapist,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
                expected_updated_at=serializer.validated_data.get("expected_updated_at"),
            )
        except Exception as error:
            raise ValidationError(str(error)) from error
        return Response(AppointmentDetailSerializer(appointment, context={"request": request}).data)


class AppointmentUnassignmentView(OperationalScopeMixin, GenericAPIView):
    serializer_class = UnassignmentSerializer

    def post(self, request, pk):
        appointment = self.scoped_queryset().filter(pk=pk).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            appointment = unassign_physiotherapist(
                appointment,
                actor=request.user,
                reason=serializer.validated_data["reason"],
                expected_updated_at=serializer.validated_data.get("expected_updated_at"),
            )
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        return Response(AppointmentDetailSerializer(appointment, context={"request": request}).data)


class OwnerAppointmentRebookView(OperationalScopeMixin, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwner)
    serializer_class = OwnerAppointmentRebookSerializer

    def post(self, request, pk):
        appointment = self.scoped_queryset().filter(pk=pk).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        physiotherapist = serializer.validated_data["physiotherapist"]
        if (
            physiotherapist.organization_id != request.organization.id
            or physiotherapist.clinic_id != appointment.clinic_id
            or physiotherapist.staff_type != Role.PHYSIOTHERAPIST
        ):
            raise ValidationError("The selected Physiotherapist is unavailable.")
        try:
            value = rebook_closed_appointment(
                appointment,
                preferred_date=serializer.validated_data["preferred_date"],
                preferred_time=serializer.validated_data["preferred_time"],
                physiotherapist=physiotherapist,
                actor=request.user,
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(
            AppointmentDetailSerializer(value, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class AppointmentAssignmentResponseView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    serializer_class = AssignmentResponseSerializer

    def post(self, request, pk):
        if (
            not active_roles(request.user, request.organization)
            .filter(role=Role.PHYSIOTHERAPIST)
            .exists()
        ):
            raise PermissionDenied("Physiotherapist access is required.")
        appointment = Appointment.objects.filter(
            pk=pk,
            organization=request.organization,
            physiotherapist__user=request.user,
        ).first()
        if appointment is None:
            raise NotFound("Assignment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            appointment = respond_to_assignment(
                appointment,
                actor=request.user,
                accept=serializer.validated_data["accept"],
                reason=serializer.validated_data.get("reason", ""),
            )
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        return Response(
            PhysiotherapistAppointmentSerializer(appointment, context={"request": request}).data
        )


class PhysiotherapistWorkloadView(OperationalScopeMixin, GenericAPIView):
    serializer_class = PhysiotherapistWorkloadSerializer

    def get(self, request):
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        profiles = StaffProfile.objects.filter(
            organization=request.organization,
            staff_type=Role.PHYSIOTHERAPIST,
            user__is_active=True,
            user__is_enabled=True,
        )
        if level == Role.MANAGER:
            profiles = profiles.filter(clinic_id__in=clinic_ids or ())
        profiles = profiles.select_related("user", "clinic").annotate(
            active_assignments=Count(
                "appointments",
                filter=Q(appointments__status__in=Appointment.BLOCKING_STATUSES),
            ),
            upcoming_assignments=Count(
                "appointments",
                filter=Q(
                    appointments__scheduled_start__gte=timezone.now(),
                    appointments__status__in=(
                        Appointment.Status.SCHEDULED,
                        Appointment.Status.CONFIRMED,
                    ),
                ),
            ),
            today_assignments=Count(
                "appointments",
                filter=Q(appointments__scheduled_start__date=timezone.localdate()),
            ),
        )
        return Response(
            [
                {
                    "id": str(profile.id),
                    "full_name": profile.user.get_full_name(),
                    "clinic": profile.clinic.name,
                    "active_assignments": profile.active_assignments,
                    "upcoming_assignments": profile.upcoming_assignments,
                    "today_assignments": profile.today_assignments,
                    "qualification": profile.qualification,
                    "availability": profile.availability,
                    "is_online": profile.is_online,
                    "service_areas": list(profile.service_areas.filter(is_active=True).values_list("name", flat=True)),
                    "specialties": list(profile.specializations.filter(is_active=True).values_list("name", flat=True)),
                    "has_photo": bool(profile.profile_photo),
                }
                for profile in profiles
            ]
        )


class AppointmentRequestDecisionView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = AppointmentRequestDecisionSerializer

    def post(self, request, pk):
        source = AppointmentRequest.objects.filter(
            pk=pk, organization=request.organization
        ).select_related("creator", "patient_profile").first()
        if source is None:
            raise NotFound("Appointment request is unavailable.")
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        patient = source.patient_profile or (
            source.creator.patient_profiles.filter(
                organization=request.organization, is_active=True
            ).first()
            if source.creator_id else None
        )
        if level == Role.MANAGER and (patient is None or patient.clinic_id not in (clinic_ids or ())):
            raise PermissionDenied("Appointment request is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            source, appointment = decide_appointment_request(
                source, actor=request.user, **serializer.validated_data
            )
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        data = AppointmentRequestSerializer(source, context={"request": request}).data
        if appointment:
            data["appointment"] = AppointmentDetailSerializer(
                appointment, context={"request": request}
            ).data
        return Response(data)


class AppointmentRequestEligiblePhysiotherapistView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)

    def get(self, request, pk):
        source = AppointmentRequest.objects.filter(
            pk=pk,
            organization=request.organization,
            status__in=(AppointmentRequest.Status.PENDING, AppointmentRequest.Status.APPROVED),
        ).select_related("creator", "patient_profile", "therapy").first()
        if source is None:
            raise NotFound("Appointment request is unavailable.")
        patient = source.patient_profile
        if patient is None and source.creator_id is not None:
            patient = source.creator.patient_profiles.filter(
                organization=request.organization, is_active=True
            ).select_related("clinic").first()
        if patient is None:
            raise NotFound("Appointment request is unavailable.")
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        if level == Role.MANAGER and patient.clinic_id not in (clinic_ids or ()):
            raise PermissionDenied("Appointment request is unavailable.")
        zone = ZoneInfo(patient.clinic.timezone or request.organization.timezone or "Asia/Kolkata")
        start = datetime.combine(source.preferred_date, source.preferred_time, zone)
        end = validate_schedule(
            clinic=patient.clinic, start=start,
            duration_minutes=source.requested_duration_minutes,
        )
        candidates = StaffProfile.objects.filter(
            organization=request.organization, clinic=patient.clinic,
            staff_type=Role.PHYSIOTHERAPIST,
        ).select_related("user", "practitioner_profile__source_application").annotate(
            approved_rating=Avg(
                "appointmentrating__stars",
                filter=Q(
                    appointmentrating__moderation_status=AppointmentRating.ModerationStatus.APPROVED
                ),
            ),
            approved_review_count=Count(
                "appointmentrating",
                filter=Q(
                    appointmentrating__moderation_status=AppointmentRating.ModerationStatus.APPROVED
                ),
                distinct=True,
            ),
        )
        result = []
        for profile in candidates:
            eligibility_reason = "Available for this requested time"
            eligible = True
            try:
                ensure_request_practitioner_eligible(
                    source=source, physiotherapist=profile, start=start, end=end
                )
            except DjangoValidationError as error:
                eligible = False
                eligibility_reason = " ".join(error.messages)
            practitioner = getattr(profile, "practitioner_profile", None)
            from apps.practitioners.dob import derived_age
            from apps.staff.photos import profile_photo
            required_ids = {
                source.therapy_id,
                *source.requested_therapies.values_list("id", flat=True),
            }
            result.append({
                "id": str(profile.id), "full_name": profile.user.get_full_name(),
                "qualification": profile.qualification,
                "age": derived_age(profile),
                "experience_years": profile.experience_years,
                "experience_months": profile.experience_months,
                "specialization": (
                    practitioner.qualification_specialization if practitioner else ""
                ),
                "expertise": list(
                    profile.therapy_competencies.filter(id__in=required_ids)
                    .order_by("name").values_list("name", flat=True)
                ),
                "rating": profile.approved_rating,
                "review_count": profile.approved_review_count,
                "has_photo": bool(profile_photo(profile)),
                "eligible": eligible,
                "eligibility_reason": eligibility_reason,
            })
        return Response(result)


class AppointmentRescheduleView(OperationalScopeMixin, GenericAPIView):
    serializer_class = AppointmentRescheduleSerializer

    def post(self, request, pk):
        appointment = self.scoped_queryset().filter(pk=pk).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        level, _ = actor_role_scope(request.user, request.organization)
        requested_override = serializer.validated_data["override"]
        if requested_override and level != Role.OWNER:
            record_rejected_lifecycle_action(
                appointment,
                actor=request.user,
                event=AppointmentAuditEvent.Event.RESCHEDULE_REJECTED,
                code="MANAGER_OVERRIDE_DENIED",
            )
            raise PermissionDenied("Managers cannot override appointment policies.")
        try:
            appointment = reschedule_appointment(
                appointment,
                scheduled_start=serializer.validated_data["scheduled_start"],
                duration_minutes=serializer.validated_data["duration_minutes"],
                actor=request.user,
                allow_override=requested_override and level == Role.OWNER,
                override_reason=serializer.validated_data.get("override_reason", ""),
            )
        except Exception as error:
            raise ValidationError(str(error)) from error
        return Response(AppointmentDetailSerializer(appointment, context={"request": request}).data)


class AppointmentCancellationView(OperationalScopeMixin, GenericAPIView):
    serializer_class = AppointmentCancellationSerializer

    def post(self, request, pk):
        appointment = self.scoped_queryset().filter(pk=pk).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        level, _ = actor_role_scope(request.user, request.organization)
        requested_override = serializer.validated_data["override"]
        if requested_override and level != Role.OWNER:
            record_rejected_lifecycle_action(
                appointment,
                actor=request.user,
                event=AppointmentAuditEvent.Event.CANCELLATION_REJECTED,
                code="MANAGER_OVERRIDE_DENIED",
            )
            raise PermissionDenied("Managers cannot override appointment policies.")
        try:
            appointment = cancel_appointment(
                appointment,
                category=serializer.validated_data["reason_category"],
                reason=serializer.validated_data["operational_reason"],
                actor=request.user,
                allow_override=requested_override and level == Role.OWNER,
                override_reason=serializer.validated_data.get("override_reason", ""),
            )
        except Exception as error:
            raise ValidationError(str(error)) from error
        return Response(AppointmentDetailSerializer(appointment, context={"request": request}).data)


class AppointmentAuditListView(OperationalScopeMixin, generics.ListAPIView):
    serializer_class = AppointmentAuditSerializer
    pagination_class = AppointmentPagination

    def get_queryset(self):
        appointment = self.scoped_queryset().filter(pk=self.kwargs["pk"]).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        return appointment.audit_events.select_related(
            "actor", "previous_physiotherapist__user", "new_physiotherapist__user"
        )


class AppointmentStatusView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    serializer_class = AppointmentStatusSerializer

    def post(self, request, pk):
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        roles = active_roles(request.user, request.organization)
        if level is None and roles.filter(role=Role.PHYSIOTHERAPIST).exists():
            level = Role.PHYSIOTHERAPIST
        queryset = Appointment.objects.filter(organization=request.organization).select_related(
            "clinic", "patient", "therapy", "physiotherapist__user", "originating_request", "payment"
        )
        if level == Role.MANAGER:
            queryset = queryset.filter(clinic_id__in=clinic_ids or ())
        elif level == Role.PHYSIOTHERAPIST:
            queryset = queryset.filter(physiotherapist__user=request.user)
        elif level != Role.OWNER:
            raise PermissionDenied("Appointment status access is unavailable.")
        appointment = queryset.filter(pk=pk).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["status"]
        if level == Role.PHYSIOTHERAPIST and (appointment.status, new_status) not in (
            (Appointment.Status.CONFIRMED, Appointment.Status.IN_PROGRESS),
            (Appointment.Status.CONFIRMED, Appointment.Status.NO_SHOW),
        ):
            raise PermissionDenied("Physiotherapists cannot perform this status change.")
        try:
            appointment = transition_status(
                appointment,
                new_status=new_status,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except Exception as error:
            raise ValidationError(str(error)) from error
        response_serializer = (
            PhysiotherapistAppointmentSerializer
            if level == Role.PHYSIOTHERAPIST
            else AppointmentDetailSerializer
        )
        return Response(response_serializer(appointment, context={"request": request}).data)


class AppointmentCompletionPaymentView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    serializer_class = AppointmentCompletionPaymentSerializer

    def post(self, request, pk):
        appointment = Appointment.objects.filter(
            pk=pk,
            organization=request.organization,
            physiotherapist__user=request.user,
        ).select_related(
            "clinic",
            "patient",
            "therapy",
            "physiotherapist__user",
            "originating_request",
            "assigned_by",
            "payment",
            "payment__updated_by",
        ).first()
        if appointment is None:
            raise NotFound("Appointment is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = getattr(appointment, "payment", None)
        if (
            (payment is None or payment.status != AppointmentPayment.Status.PAID)
            and not serializer.validated_data.get("payment_received")
        ):
            raise ValidationError(
                "Confirm customer payment for this historical post-service payment flow."
            )
        try:
            appointment = complete_and_confirm_payment(appointment, actor=request.user)
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(
            PhysiotherapistAppointmentSerializer(
                appointment, context={"request": request}
            ).data
        )


class AppointmentJourneyView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    serializer_class = JourneyUpdateSerializer

    def post(self, request, pk):
        appointment = Appointment.objects.filter(
            pk=pk, organization=request.organization, physiotherapist__user=request.user
        ).select_related("physiotherapist__user", "patient", "therapy", "clinic", "originating_request").first()
        if appointment is None:
            raise NotFound("Visit is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            appointment = update_journey(appointment, actor=request.user, **serializer.validated_data)
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        return Response(PhysiotherapistAppointmentSerializer(appointment, context={"request": request}).data)

class AvailablePhysiotherapistView(OperationalScopeMixin, GenericAPIView):
    serializer_class = AvailabilityQuerySerializer

    def get(self, request):
        query = self.get_serializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        clinic_id = query.validated_data["clinic"]
        start = query.validated_data["scheduled_start"]
        duration = query.validated_data["duration_minutes"]
        exclude_appointment = request.query_params.get("exclude_appointment")
        clinic = self.request.organization.clinics.filter(pk=clinic_id, is_active=True).first()
        if clinic is None:
            raise NotFound("Clinic is unavailable.")
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        if level == Role.MANAGER and clinic.id not in (clinic_ids or ()):
            raise PermissionDenied("Clinic is unavailable.")
        end = validate_schedule(clinic=clinic, start=start, duration_minutes=duration)
        busy = Appointment.objects.filter(
            clinic=clinic,
            status__in=Appointment.BLOCKING_STATUSES,
            scheduled_start__lt=end,
            scheduled_end__gt=start,
        )
        if exclude_appointment:
            if not self.scoped_queryset().filter(pk=exclude_appointment, clinic=clinic).exists():
                raise NotFound("Appointment is unavailable.")
            busy = busy.exclude(pk=exclude_appointment)
        busy = busy.values_list("physiotherapist_id", flat=True)
        profiles = (
            StaffProfile.objects.filter(
                organization=request.organization,
                clinic=clinic,
                staff_type=Role.PHYSIOTHERAPIST,
                user__is_active=True,
                user__is_enabled=True,
            )
            .exclude(pk__in=busy)
            .filter(
                user__role_assignments__organization=request.organization,
                user__role_assignments__clinic=clinic,
                user__role_assignments__role=Role.PHYSIOTHERAPIST,
                user__role_assignments__is_active=True,
            )
            .filter(
                Q(practitioner_profile__isnull=True)
                | Q(
                    practitioner_profile__is_approved=True,
                    practitioner_profile__is_open_to_work=True,
                )
            )
            .select_related("user")
        )
        available = []
        for profile in profiles:
            try:
                ensure_physiotherapist_available(
                    physiotherapist=profile,
                    clinic=clinic,
                    start=start,
                    end=end,
                )
            except DjangoValidationError:
                continue
            available.append({"id": str(profile.id), "full_name": profile.user.get_full_name()})
        return Response(available)


class MyAssignedAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    serializer_class = PhysiotherapistAppointmentSerializer

    def get_queryset(self):
        if (
            not active_roles(self.request.user, self.request.organization)
            .filter(role=Role.PHYSIOTHERAPIST)
            .exists()
        ):
            raise PermissionDenied("Physiotherapist access is required.")
        return Appointment.objects.filter(
            organization=self.request.organization,
            physiotherapist__user=self.request.user,
        ).select_related(
            "clinic",
            "patient",
            "therapy",
            "physiotherapist__user",
            "originating_request",
            "assigned_by",
            "payment",
            "payment__updated_by",
        )


class CustomerOperationalAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerAppointmentSerializer

    def get_queryset(self):
        return Appointment.objects.filter(organization=self.request.organization).filter(
            Q(originating_request__creator=self.request.user) | Q(patient__user=self.request.user)
        ).select_related(
            "clinic", "patient", "therapy", "physiotherapist__user", "originating_request",
            "physiotherapist__practitioner_profile", "payment", "payment__updated_by", "rating",
        ).prefetch_related(
            "originating_request__requested_therapies",
            "physiotherapist__therapy_competencies",
            "physiotherapist__specializations",
        )


class CustomerAppointmentChangeRequestView(HasTenant, generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AppointmentChangeRequestSerializer

    def get_queryset(self):
        return AppointmentChangeRequest.objects.filter(organization=self.request.organization).filter(
            Q(appointment__originating_request__creator=self.request.user) | Q(appointment__patient__user=self.request.user)
        ).select_related("appointment")

    def perform_create(self, serializer):
        appointment = Appointment.objects.filter(
            pk=self.kwargs["pk"],
            organization=self.request.organization,
            status__in=(
                Appointment.Status.DRAFT,
                Appointment.Status.PENDING_ASSIGNMENT,
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
            ),
        ).filter(Q(originating_request__creator=self.request.user) | Q(patient__user=self.request.user)).first()
        if appointment is None:
            raise NotFound("Appointment change requests are unavailable.")
        payment = getattr(appointment, "payment", None)
        if payment is not None and payment.status == AppointmentPayment.Status.PAID:
            raise ValidationError(
                "Confirmed prepaid appointments cannot be cancelled or refunded through the booking flow."
            )
        try:
            with transaction.atomic():
                value = serializer.save(
                    appointment=appointment,
                    organization=self.request.organization,
                    requested_by=self.request.user,
                )
                AppointmentAuditEvent.objects.create(
                    appointment=appointment,
                    organization=self.request.organization,
                    actor=self.request.user,
                    event=AppointmentAuditEvent.Event.CUSTOMER_CHANGE_REQUESTED,
                    reason=value.kind,
                )
        except IntegrityError as error:
            raise ValidationError("An equivalent change request is already pending.") from error


class AppointmentPhysiotherapistPhotoView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    serializer_class = CustomerAppointmentSerializer

    def get(self, request, pk):
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        roles = active_roles(request.user, request.organization)
        if level is None and roles.filter(role=Role.PHYSIOTHERAPIST).exists():
            level = Role.PHYSIOTHERAPIST
        elif level is None and roles.filter(role=Role.CUSTOMER).exists():
            level = Role.CUSTOMER
        queryset = Appointment.objects.filter(organization=request.organization)
        if level == Role.MANAGER:
            queryset = queryset.filter(clinic_id__in=clinic_ids or ())
        elif level == Role.PHYSIOTHERAPIST:
            queryset = queryset.filter(physiotherapist__user=request.user)
        elif level == Role.CUSTOMER:
            queryset = queryset.filter(
                originating_request__creator=request.user,
                assignment_status__in=(
                    Appointment.AssignmentStatus.PENDING,
                    Appointment.AssignmentStatus.ACCEPTED,
                ),
            )
        elif level != Role.OWNER:
            raise PermissionDenied("Appointment access is unavailable.")
        appointment = queryset.select_related("physiotherapist").filter(pk=pk).first()
        from apps.staff.photos import profile_photo
        photo = profile_photo(appointment.physiotherapist) if appointment and appointment.physiotherapist else None
        if appointment is None or appointment.physiotherapist is None or not photo:
            raise NotFound("Physiotherapist photograph is unavailable.")
        return FileResponse(
            photo.open("rb"),
            content_type="application/octet-stream",
        )

class CustomerAppointmentRatingView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AppointmentRatingSerializer

    def post(self, request, pk):
        try:
            with transaction.atomic():
                appointment = (
                    Appointment.objects.select_for_update(of=("self",))
                    .filter(
                        pk=pk,
                        organization=request.organization,
                        status=Appointment.Status.COMPLETED,
                        completed_at__isnull=False,
                        assignment_status=Appointment.AssignmentStatus.ACCEPTED,
                        physiotherapist__isnull=False,
                    )
                    .filter(
                        Q(originating_request__creator=request.user)
                        | Q(patient__user=request.user)
                    )
                    .first()
                )
                if appointment is None:
                    raise NotFound("Review is unavailable.")
                if AppointmentRating.objects.filter(appointment=appointment).exists():
                    raise ValidationError(
                        "Feedback has already been submitted for this appointment."
                    )
                serializer = self.get_serializer(data=request.data)
                serializer.is_valid(raise_exception=True)
                value = serializer.save(
                    appointment=appointment,
                    organization=request.organization,
                    customer=request.user,
                    physiotherapist=appointment.physiotherapist,
                )
                AppointmentAuditEvent.objects.create(
                    appointment=appointment,
                    organization=request.organization,
                    actor=request.user,
                    event=AppointmentAuditEvent.Event.RATING_SUBMITTED,
                )
                from apps.appointments.notification_events import notify_rating_submitted

                notify_rating_submitted(value)
        except IntegrityError as error:
            # The appointment row lock serializes normal requests and the database
            # one-to-one constraint remains the final guard for concurrent inserts.
            raise ValidationError(
                "Feedback has already been submitted for this appointment."
            ) from error
        return Response(self.get_serializer(value).data, status=status.HTTP_201_CREATED)


class ReviewOperationsListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = ReviewOperationsSerializer
    pagination_class = AppointmentPagination

    def get_queryset(self):
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        queryset = AppointmentRating.objects.filter(organization=self.request.organization).select_related("customer", "physiotherapist__user", "appointment__therapy", "appointment__clinic")
        if level == Role.MANAGER and clinic_ids is not None:
            queryset = queryset.filter(appointment__clinic_id__in=clinic_ids)
        params = self.request.query_params
        if params.get("physiotherapist"):
            queryset = queryset.filter(physiotherapist_id=params["physiotherapist"])
        if params.get("therapist"):
            queryset = queryset.filter(
                Q(physiotherapist__user__first_name__icontains=params["therapist"])
                | Q(physiotherapist__user__last_name__icontains=params["therapist"])
            )
        if params.get("rating"):
            queryset = queryset.filter(stars=params["rating"])
        if params.get("status"):
            queryset = queryset.filter(moderation_status=params["status"])
        if params.get("date_from"):
            queryset = queryset.filter(created_at__date__gte=params["date_from"])
        if params.get("date_to"):
            queryset = queryset.filter(created_at__date__lte=params["date_to"])
        return queryset.order_by("-created_at")


class ReviewModerationView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwner)
    serializer_class = ReviewModerationSerializer

    def post(self, request, pk):
        queryset = AppointmentRating.objects.filter(pk=pk, organization=request.organization)
        review = queryset.first()
        if review is None:
            raise NotFound("Review is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        previous = review.moderation_status
        review.moderation_status = serializer.validated_data["moderation_status"]
        review.moderation_reason = serializer.validated_data.get("reason", "")
        review.moderated_by = request.user
        review.moderated_at = timezone.now()
        review.save(update_fields=("moderation_status", "moderation_reason", "moderated_by", "moderated_at"))
        AppointmentRatingModerationEvent.objects.create(rating=review, organization=request.organization, actor=request.user, previous_status=previous, new_status=review.moderation_status, reason=review.moderation_reason)
        return Response(ReviewOperationsSerializer(review).data)


class PublicReviewListView(HasTenant, GenericAPIView):
    permission_classes = (permissions.AllowAny,)

    def get(self, request):
        queryset = AppointmentRating.objects.filter(organization=request.organization, moderation_status=AppointmentRating.ModerationStatus.APPROVED).select_related("customer", "physiotherapist__user").order_by("-created_at")
        aggregate = queryset.aggregate(average_rating=Avg("stars"), review_count=Count("id"))
        return Response({"average_rating": aggregate["average_rating"], "review_count": aggregate["review_count"], "reviews": PublicReviewSerializer(queryset[:20], many=True).data})


class PractitionerReviewListView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)

    def get(self, request):
        queryset = AppointmentRating.objects.filter(organization=request.organization, physiotherapist__user=request.user).select_related("customer", "physiotherapist__user", "appointment__therapy").order_by("-created_at")
        approved = queryset.filter(moderation_status=AppointmentRating.ModerationStatus.APPROVED)
        aggregate = approved.aggregate(average_rating=Avg("stars"), review_count=Count("id"))
        return Response({"average_rating": aggregate["average_rating"], "review_count": aggregate["review_count"], "reviews": ReviewOperationsSerializer(queryset, many=True).data})


class PractitionerPaymentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    serializer_class = PractitionerPaymentSerializer

    def get_queryset(self):
        return PractitionerPayment.objects.filter(organization=self.request.organization, physiotherapist__user=self.request.user).select_related("appointment__therapy")


class OperationsPaymentView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = AppointmentPaymentSerializer

    def post(self, request, pk):
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        appointment = Appointment.objects.select_related("originating_request", "payment").filter(
            pk=pk, organization=request.organization
        ).first()
        if appointment is None or (level == Role.MANAGER and appointment.clinic_id not in (clinic_ids or ())):
            raise NotFound("Payment is unavailable.")
        existing_payment = getattr(appointment, "payment", None)
        if existing_payment and existing_payment.status == AppointmentPayment.Status.VERIFICATION_PENDING:
            if level != Role.OWNER:
                raise PermissionDenied("Only an Owner may verify a customer payment.")
            try:
                appointment = verify_customer_payment(
                    appointment,
                    actor=request.user,
                    reference=str(request.data.get("reference", "")),
                    note=str(request.data.get("note", "")),
                )
            except DjangoValidationError as error:
                raise ValidationError(error.messages) from error
            return Response(self.get_serializer(appointment.payment).data)
        if appointment.status != Appointment.Status.COMPLETED or appointment.physiotherapist_id is None:
            raise NotFound("Payment is unavailable.")
        source = appointment.originating_request
        amount_due = source.final_amount if source and source.final_amount is not None else 0
        value, _ = AppointmentPayment.objects.get_or_create(
            appointment=appointment,
            defaults={"organization": request.organization, "amount_due": amount_due, "updated_by": request.user},
        )
        previous_status = value.status
        serializer = self.get_serializer(value, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = serializer.save(
            updated_by=request.user,
            paid_at=(timezone.now() if serializer.validated_data.get("status") == AppointmentPayment.Status.PAID and value.status != AppointmentPayment.Status.PAID else value.paid_at),
        )
        AppointmentAuditEvent.objects.create(appointment=appointment, organization=request.organization, actor=request.user, event="PAYMENT_STATUS_CHANGED", reason=value.status)
        if previous_status != AppointmentPayment.Status.PAID and value.status == AppointmentPayment.Status.PAID:
            from apps.appointments.notification_events import notify_payment_confirmed

            notify_payment_confirmed(appointment)
        return Response(self.get_serializer(value).data)
