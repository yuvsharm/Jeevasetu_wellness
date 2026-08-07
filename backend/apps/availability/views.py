from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsEnabledAuthenticated, IsOwnerOrManager, IsPhysiotherapist
from apps.accounts.role_policy import actor_role_scope
from apps.appointments.models import TherapyOption
from apps.availability.models import (
    ApprovalStatus,
    AvailabilityAuditEvent,
    AvailabilityException,
    AvailabilityRule,
)
from apps.availability.serializers import (
    AuditSerializer,
    DeactivateSerializer,
    ExceptionSerializer,
    ReviewSerializer,
    RuleSerializer,
    SelfExceptionSerializer,
    SelfRuleSerializer,
    SlotQuerySerializer,
    validate_profile,
)
from apps.availability.services import (
    discover_slots,
    record_event,
    review_availability,
    validate_exception,
    validate_for_approval,
    validate_rule,
)
from apps.staff.models import StaffProfile


class Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class OperationsMixin:
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(request, "organization", None):
            raise NotFound("Organization context is unavailable.")

    def scope(self, queryset):
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        queryset = queryset.filter(organization=self.request.organization)
        if level == Role.MANAGER:
            queryset = queryset.filter(clinic_id__in=clinic_ids or ())
        return queryset

    def assert_clinic(self, clinic):
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        if clinic.organization_id != self.request.organization.id:
            raise PermissionDenied("Clinic is unavailable.")
        if level == Role.MANAGER and clinic.id not in (clinic_ids or ()):
            raise PermissionDenied("Clinic is unavailable.")


class OperationsCollection(OperationsMixin, generics.ListCreateAPIView):
    pagination_class = Pagination
    model = None

    def get_queryset(self):
        queryset = self.scope(self.model.objects.select_related("clinic", "physiotherapist__user"))
        for key in ("clinic", "physiotherapist", "approval_status"):
            value = self.request.query_params.get(key)
            if value:
                queryset = queryset.filter(**{key: value})
        return queryset

    def perform_create(self, serializer):
        clinic = serializer.validated_data["clinic"]
        profile = serializer.validated_data["physiotherapist"]
        self.assert_clinic(clinic)
        validate_profile(profile, self.request.organization, clinic)
        value = self.model(
            organization=self.request.organization,
            submitted_by=self.request.user,
            **serializer.validated_data,
        )
        try:
            value.full_clean()
            value.save()
            record_event(
                value, actor=self.request.user, action=AvailabilityAuditEvent.Action.CREATED
            )
            value = review_availability(value, actor=self.request.user, approve=True)
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        serializer.instance = value


class RuleCollectionView(OperationsCollection):
    model = AvailabilityRule
    serializer_class = RuleSerializer


class ExceptionCollectionView(OperationsCollection):
    model = AvailabilityException
    serializer_class = ExceptionSerializer


class OperationsObjectMixin(OperationsMixin):
    model = None

    def object(self, pk):
        value = self.scope(self.model.objects.all()).filter(pk=pk).first()
        if value is None:
            raise NotFound("Availability record is unavailable.")
        return value


class RuleDetailView(OperationsObjectMixin, generics.RetrieveUpdateAPIView):
    model = AvailabilityRule
    serializer_class = RuleSerializer

    def get_queryset(self):
        return self.scope(self.model.objects.all())

    def perform_update(self, serializer):
        if any(key in serializer.validated_data for key in ("clinic", "physiotherapist")):
            raise PermissionDenied("Availability scope cannot be changed.")
        value = serializer.instance
        for key, item in serializer.validated_data.items():
            setattr(value, key, item)
        try:
            validate_rule(value)
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        value = serializer.save()
        record_event(value, actor=self.request.user, action=AvailabilityAuditEvent.Action.EDITED)


class ExceptionDetailView(OperationsObjectMixin, generics.RetrieveUpdateAPIView):
    model = AvailabilityException
    serializer_class = ExceptionSerializer

    def get_queryset(self):
        return self.scope(self.model.objects.all())

    def perform_update(self, serializer):
        if any(key in serializer.validated_data for key in ("clinic", "physiotherapist")):
            raise PermissionDenied("Availability scope cannot be changed.")
        value = serializer.instance
        for key, item in serializer.validated_data.items():
            setattr(value, key, item)
        try:
            validate_for_approval(value) if value.is_active else validate_exception(value)
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        value = serializer.save()
        record_event(value, actor=self.request.user, action=AvailabilityAuditEvent.Action.EDITED)


class ReviewView(OperationsObjectMixin, GenericAPIView):
    serializer_class = ReviewSerializer

    def post(self, request, pk):
        value = self.object(pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            value = review_availability(
                value,
                actor=request.user,
                approve=serializer.validated_data["approve"],
                reason=serializer.validated_data.get("reason", ""),
            )
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        output = RuleSerializer if isinstance(value, AvailabilityRule) else ExceptionSerializer
        return Response(output(value).data)


class RuleReviewView(ReviewView):
    model = AvailabilityRule


class ExceptionReviewView(ReviewView):
    model = AvailabilityException


class DeactivateView(OperationsObjectMixin, GenericAPIView):
    serializer_class = DeactivateSerializer

    def post(self, request, pk):
        value = self.object(pk)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        value.is_active = False
        value.save(update_fields=("is_active", "updated_at"))
        record_event(
            value,
            actor=request.user,
            action=AvailabilityAuditEvent.Action.DEACTIVATED,
            reason=serializer.validated_data["reason"],
        )
        output = RuleSerializer if isinstance(value, AvailabilityRule) else ExceptionSerializer
        return Response(output(value).data)


class RuleDeactivateView(DeactivateView):
    model = AvailabilityRule


class ExceptionDeactivateView(DeactivateView):
    model = AvailabilityException


class SelfCollection(generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    pagination_class = Pagination
    model = None

    def profile(self):
        value = StaffProfile.objects.filter(
            user=self.request.user,
            organization=self.request.organization,
            staff_type=Role.PHYSIOTHERAPIST,
        ).first()
        if value is None:
            raise NotFound("Physiotherapist profile is unavailable.")
        return value

    def get_queryset(self):
        return self.model.objects.filter(
            organization=self.request.organization, physiotherapist=self.profile()
        ).select_related("clinic", "physiotherapist__user")

    def perform_create(self, serializer):
        profile = self.profile()
        if serializer.validated_data.get("physiotherapist", profile) != profile:
            raise PermissionDenied("Only your own availability may be submitted.")
        value = self.model(
            organization=self.request.organization,
            clinic=profile.clinic,
            physiotherapist=profile,
            submitted_by=self.request.user,
            approval_status=ApprovalStatus.PENDING,
            is_active=False,
            **{
                key: item
                for key, item in serializer.validated_data.items()
                if key not in ("clinic", "physiotherapist")
            },
        )
        try:
            value.full_clean()
            value.save()
        except DjangoValidationError as error:
            raise ValidationError(str(error)) from error
        record_event(value, actor=self.request.user, action=AvailabilityAuditEvent.Action.SUBMITTED)
        serializer.instance = value


class SelfRuleView(SelfCollection):
    model = AvailabilityRule
    serializer_class = SelfRuleSerializer


class SelfExceptionView(SelfCollection):
    model = AvailabilityException
    serializer_class = SelfExceptionSerializer


class SlotDiscoveryView(OperationsMixin, GenericAPIView):
    serializer_class = SlotQuerySerializer

    def get(self, request):
        serializer = self.get_serializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        clinic = request.organization.clinics.filter(pk=data["clinic"], is_active=True).first()
        if clinic is None:
            raise NotFound("Clinic is unavailable.")
        self.assert_clinic(clinic)
        therapy = TherapyOption.objects.filter(
            pk=data["therapy"], organization=request.organization, is_active=True
        ).first()
        if therapy is None:
            raise NotFound("Therapy is unavailable.")
        profile = None
        if data.get("physiotherapist"):
            profile = StaffProfile.objects.filter(
                pk=data["physiotherapist"], organization=request.organization, clinic=clinic
            ).first()
            if profile is None:
                raise NotFound("Physiotherapist is unavailable.")
        return Response(
            discover_slots(
                clinic=clinic,
                therapy=therapy,
                date_from=data["date_from"],
                date_to=data["date_to"],
                physiotherapist=profile,
            )
        )


class AuditView(OperationsMixin, generics.ListAPIView):
    serializer_class = AuditSerializer
    pagination_class = Pagination

    def get_queryset(self):
        return self.scope(
            AvailabilityAuditEvent.objects.select_related("actor", "physiotherapist__user")
        )
