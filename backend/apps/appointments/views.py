from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.http import FileResponse
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
    IsOwnerOrManager,
    IsPhysiotherapist,
    active_roles,
)
from apps.accounts.role_policy import actor_role_scope
from apps.appointments.models import (
    Appointment,
    AppointmentAuditEvent,
    AppointmentChangeRequest,
    AppointmentRequest,
    AppointmentRating,
    PractitionerPayment,
    TherapyOption,
)
from apps.appointments.scheduling import (
    assign_physiotherapist,
    cancel_appointment,
    record_rejected_lifecycle_action,
    reschedule_appointment,
    respond_to_assignment,
    transition_status,
    update_journey,
    unassign_physiotherapist,
    validate_schedule,
)
from apps.appointments.serializers import (
    AppointmentAuditSerializer,
    AppointmentCancellationSerializer,
    AppointmentChangeRequestSerializer,
    AppointmentDetailSerializer,
    AppointmentListSerializer,
    AppointmentRequestSerializer,
    AppointmentRatingSerializer,
    PractitionerPaymentSerializer,
    AppointmentRescheduleSerializer,
    AppointmentStatusSerializer,
    JourneyUpdateSerializer,
    AppointmentWriteSerializer,
    AssignmentResponseSerializer,
    AssignmentSerializer,
    AvailabilityQuerySerializer,
    CancelAppointmentSerializer,
    CustomerAppointmentSerializer,
    OwnerAppointmentUpdateSerializer,
    PhysiotherapistAppointmentSerializer,
    PhysiotherapistWorkloadSerializer,
    TherapyOptionSerializer,
    UnassignmentSerializer,
    VisitOtpSubmissionSerializer,
)
from apps.appointments.visit_verification import (
    issue_visit_otp,
    verify_visit_otp,
    visit_verification_status,
)
from apps.availability.services import ensure_physiotherapist_available
from apps.staff.models import StaffProfile


class HasTenant:
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request, "organization", None) is None:
            raise NotFound("Organization context is unavailable.")


class TherapyListView(HasTenant, generics.ListAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = TherapyOptionSerializer

    def get_queryset(self):
        return TherapyOption.objects.filter(organization=self.request.organization, is_active=True)


class AppointmentCreateView(HasTenant, generics.CreateAPIView):
    permission_classes = (permissions.AllowAny,)
    serializer_class = AppointmentRequestSerializer


class CustomerAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AppointmentRequestSerializer

    def get_queryset(self):
        return AppointmentRequest.objects.filter(
            organization=self.request.organization, creator=self.request.user
        ).select_related("therapy")


class CustomerAppointmentDetailView(HasTenant, generics.RetrieveAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AppointmentRequestSerializer

    def get_queryset(self):
        return AppointmentRequest.objects.filter(
            organization=self.request.organization, creator=self.request.user
        ).select_related("therapy")


class CustomerAppointmentCancelView(CustomerAppointmentDetailView, generics.UpdateAPIView):
    serializer_class = CancelAppointmentSerializer

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data={})
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(AppointmentRequestSerializer(instance).data)


class OwnerAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = AppointmentRequestSerializer

    def get_queryset(self):
        level, _ = actor_role_scope(self.request.user, self.request.organization)
        if level not in (Role.OWNER, Role.MANAGER):
            raise PermissionDenied("Operations access is required.")
        queryset = AppointmentRequest.objects.filter(
            organization=self.request.organization
        ).select_related("therapy", "creator")
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


class OwnerAppointmentDetailView(HasTenant, generics.RetrieveUpdateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = AppointmentRequestSerializer

    def get_queryset(self):
        level, _ = actor_role_scope(self.request.user, self.request.organization)
        if level not in (Role.OWNER, Role.MANAGER):
            raise PermissionDenied("Operations access is required.")
        return AppointmentRequest.objects.filter(
            organization=self.request.organization
        ).select_related("therapy", "creator")

    def get_serializer_class(self):
        return (
            OwnerAppointmentUpdateSerializer
            if self.request.method in ("PUT", "PATCH")
            else AppointmentRequestSerializer
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
            "therapy",
            "physiotherapist__user",
            "originating_request",
            "assigned_by",
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
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(patient__full_name__icontains=search)
                | Q(patient__patient_identifier__icontains=search)
                | Q(physiotherapist__user__first_name__icontains=search)
                | Q(physiotherapist__user__last_name__icontains=search)
                | Q(assigned_by__first_name__icontains=search)
                | Q(assigned_by__last_name__icontains=search)
                | Q(status__icontains=search)
            )
        view = self.request.query_params.get("view")
        today = timezone.localdate()
        if view == "today":
            queryset = queryset.filter(scheduled_start__date=today)
        elif view == "upcoming":
            queryset = queryset.filter(scheduled_start__date__gt=today).exclude(
                status=Appointment.Status.CANCELLED
            )
        elif view == "cancelled":
            queryset = queryset.filter(status=Appointment.Status.CANCELLED)
        date_from = self.request.query_params.get("date_from")
        date_to = self.request.query_params.get("date_to")
        if date_from:
            queryset = queryset.filter(scheduled_start__date__gte=date_from)
        if date_to:
            queryset = queryset.filter(scheduled_start__date__lte=date_to)
        return queryset

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
        if not self.request.query_params.get("status"):
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
                appointment, actor=request.user, reason=serializer.validated_data["reason"]
            )
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        return Response(AppointmentDetailSerializer(appointment, context={"request": request}).data)


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
        )
        return Response(
            [
                {
                    "id": str(profile.id),
                    "full_name": profile.user.get_full_name(),
                    "clinic": profile.clinic.name,
                    "active_assignments": profile.active_assignments,
                    "upcoming_assignments": profile.upcoming_assignments,
                }
                for profile in profiles
            ]
        )


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
            "clinic", "patient", "therapy", "physiotherapist__user"
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
            (Appointment.Status.IN_PROGRESS, Appointment.Status.COMPLETED),
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
        ).values_list("physiotherapist_id", flat=True)
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
        )


class CustomerOperationalAppointmentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerAppointmentSerializer

    def get_queryset(self):
        return Appointment.objects.filter(
            organization=self.request.organization,
            patient__user=self.request.user,
        ).select_related("clinic", "patient", "therapy", "physiotherapist__user")


class CustomerAppointmentChangeRequestView(HasTenant, generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AppointmentChangeRequestSerializer

    def get_queryset(self):
        return AppointmentChangeRequest.objects.filter(
            organization=self.request.organization,
            appointment__patient__user=self.request.user,
        ).select_related("appointment")

    def perform_create(self, serializer):
        appointment = Appointment.objects.filter(
            pk=self.kwargs["pk"],
            organization=self.request.organization,
            patient__user=self.request.user,
            status__in=(
                Appointment.Status.DRAFT,
                Appointment.Status.PENDING_ASSIGNMENT,
                Appointment.Status.SCHEDULED,
                Appointment.Status.CONFIRMED,
            ),
        ).first()
        if appointment is None:
            raise NotFound("Appointment change requests are unavailable.")
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


class CustomerVisitVerificationView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerAppointmentSerializer

    def get_appointment(self, request, pk):
        appointment = (
            Appointment.objects.filter(
                pk=pk,
                organization=request.organization,
                patient__user=request.user,
            )
            .select_related(
                "organization",
                "clinic",
                "patient__user",
                "physiotherapist__user",
            )
            .first()
        )
        if appointment is None:
            raise NotFound("Visit verification is unavailable.")
        return appointment

    def get(self, request, pk):
        appointment = self.get_appointment(request, pk)
        return Response(visit_verification_status(appointment, actor=request.user))

    def post(self, request, pk):
        appointment = self.get_appointment(request, pk)
        try:
            verification, delivery = issue_visit_otp(appointment, customer=request.user)
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        response = visit_verification_status(appointment, actor=request.user)
        response.update(
            {
                "otp": delivery.otp,
                "expires_at": delivery.expires_at,
                "verification_id": str(verification.id),
            }
        )
        return Response(response, status=status.HTTP_201_CREATED)


class PhysiotherapistVisitVerificationView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    serializer_class = VisitOtpSubmissionSerializer

    def get_appointment(self, request, pk):
        appointment = (
            Appointment.objects.filter(pk=pk, organization=request.organization)
            .select_related(
                "organization",
                "clinic",
                "patient__user",
                "physiotherapist__user",
            )
            .first()
        )
        if appointment is None:
            raise NotFound("Visit verification is unavailable.")
        return appointment

    def get(self, request, pk):
        appointment = self.get_appointment(request, pk)
        if (
            appointment.physiotherapist is None
            or appointment.physiotherapist.user_id != request.user.id
        ):
            raise NotFound("Visit verification is unavailable.")
        return Response(visit_verification_status(appointment, actor=request.user))

    def post(self, request, pk):
        appointment = self.get_appointment(request, pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            verification = verify_visit_otp(
                appointment,
                physiotherapist_user=request.user,
                otp=serializer.validated_data["otp"],
            )
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        return Response(
            {
                "status": "VERIFIED",
                "verified_at": verification.verified_at,
                "expires_at": None,
                "failed_attempt_warning": verification.failed_attempt_count > 0,
            }
        )


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
            queryset = queryset.filter(patient__user=request.user)
        elif level != Role.OWNER:
            raise PermissionDenied("Appointment access is unavailable.")
        appointment = queryset.select_related("physiotherapist").filter(pk=pk).first()
        if (
            appointment is None
            or appointment.physiotherapist is None
            or not appointment.physiotherapist.profile_photo
        ):
            raise NotFound("Physiotherapist photograph is unavailable.")
        return FileResponse(
            appointment.physiotherapist.profile_photo.open("rb"),
            content_type="application/octet-stream",
        )

class CustomerAppointmentRatingView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = AppointmentRatingSerializer

    def post(self, request, pk):
        appointment = Appointment.objects.filter(pk=pk, organization=request.organization, patient__user=request.user, status=Appointment.Status.COMPLETED, physiotherapist__isnull=False).first()
        if appointment is None:
            raise NotFound("Rating is unavailable.")
        if AppointmentRating.objects.filter(appointment=appointment).exists():
            raise ValidationError("This appointment has already been rated.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value = serializer.save(appointment=appointment, organization=request.organization, customer=request.user, physiotherapist=appointment.physiotherapist)
        AppointmentAuditEvent.objects.create(appointment=appointment, organization=request.organization, actor=request.user, event="RATING_SUBMITTED")
        return Response(self.get_serializer(value).data, status=status.HTTP_201_CREATED)


class PractitionerPaymentListView(HasTenant, generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    serializer_class = PractitionerPaymentSerializer

    def get_queryset(self):
        return PractitionerPayment.objects.filter(organization=self.request.organization, physiotherapist__user=self.request.user).select_related("appointment__therapy")


class OperationsPaymentView(HasTenant, GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = PractitionerPaymentSerializer

    def post(self, request, pk):
        level, clinic_ids = actor_role_scope(request.user, request.organization)
        appointment = Appointment.objects.filter(pk=pk, organization=request.organization, status=Appointment.Status.COMPLETED, physiotherapist__isnull=False).first()
        if appointment is None or (level == Role.MANAGER and appointment.clinic_id not in (clinic_ids or ())):
            raise NotFound("Payment is unavailable.")
        value, _ = PractitionerPayment.objects.get_or_create(appointment=appointment, defaults={"organization": request.organization, "physiotherapist": appointment.physiotherapist, "updated_by": request.user})
        serializer = self.get_serializer(value, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        value = serializer.save(updated_by=request.user, paid_at=timezone.now() if serializer.validated_data.get("status") == PractitionerPayment.Status.PAID else value.paid_at)
        AppointmentAuditEvent.objects.create(appointment=appointment, organization=request.organization, actor=request.user, event="PAYMENT_STATUS_CHANGED", reason=value.status)
        return Response(self.get_serializer(value).data)