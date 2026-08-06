from django.db.models import Q
from rest_framework import generics, permissions
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsCustomer, IsEnabledAuthenticated, IsOwner, active_roles
from apps.appointments.models import AppointmentRequest, TherapyOption
from apps.appointments.serializers import (
    AppointmentRequestSerializer,
    CancelAppointmentSerializer,
    OwnerAppointmentUpdateSerializer,
    TherapyOptionSerializer,
)


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
    permission_classes = (IsEnabledAuthenticated, IsOwner)
    serializer_class = AppointmentRequestSerializer

    def get_queryset(self):
        if (
            not active_roles(self.request.user, self.request.organization)
            .filter(role=Role.OWNER, clinic__isnull=True)
            .exists()
        ):
            raise PermissionDenied("Owner access is required.")
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
    permission_classes = (IsEnabledAuthenticated, IsOwner)
    serializer_class = AppointmentRequestSerializer

    def get_queryset(self):
        if (
            not active_roles(self.request.user, self.request.organization)
            .filter(role=Role.OWNER, clinic__isnull=True)
            .exists()
        ):
            raise PermissionDenied("Owner access is required.")
        return AppointmentRequest.objects.filter(
            organization=self.request.organization
        ).select_related("therapy", "creator")

    def get_serializer_class(self):
        return (
            OwnerAppointmentUpdateSerializer
            if self.request.method in ("PUT", "PATCH")
            else AppointmentRequestSerializer
        )
