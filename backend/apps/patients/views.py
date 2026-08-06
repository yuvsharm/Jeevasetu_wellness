from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import FileResponse
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsEnabledAuthenticated, IsOwnerOrManager
from apps.accounts.role_policy import actor_role_scope
from apps.patients.models import PatientProfile, PatientStatusAudit
from apps.patients.serializers import (
    PatientListSerializer,
    PatientProfileSerializer,
    PatientStatusSerializer,
)


class PatientTenantMixin:
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request, "organization", None) is None:
            raise NotFound("Organization context is unavailable.")

    def scoped_queryset(self):
        queryset = PatientProfile.objects.filter(
            organization=self.request.organization
        ).select_related("clinic")
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        if level == Role.MANAGER:
            queryset = queryset.filter(clinic_id__in=clinic_ids or ())
        return queryset.prefetch_related("addresses", "caregivers")


class PatientPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class PatientListCreateView(PatientTenantMixin, generics.ListCreateAPIView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    pagination_class = PatientPagination

    def get_serializer_class(self):
        return PatientProfileSerializer if self.request.method == "POST" else PatientListSerializer

    def get_queryset(self):
        queryset = self.scoped_queryset()
        search = self.request.query_params.get("search", "").strip()
        state = self.request.query_params.get("status", "")
        clinic = self.request.query_params.get("clinic", "")
        ordering = self.request.query_params.get("ordering", "full_name")
        if search:
            queryset = queryset.filter(
                Q(full_name__icontains=search)
                | Q(patient_identifier__icontains=search)
                | Q(mobile_number__icontains=search)
            )
        if state in ("active", "inactive"):
            queryset = queryset.filter(is_active=state == "active")
        if clinic:
            queryset = queryset.filter(clinic_id=clinic)
        if ordering.lstrip("-") not in ("full_name", "created_at", "patient_identifier"):
            ordering = "full_name"
        return queryset.order_by(ordering)


class PatientDetailView(PatientTenantMixin, generics.RetrieveUpdateAPIView):
    serializer_class = PatientProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        return self.scoped_queryset()


class PatientStatusView(PatientTenantMixin, GenericAPIView):
    serializer_class = PatientStatusSerializer

    def post(self, request, pk):
        patient = self.scoped_queryset().filter(pk=pk).first()
        if patient is None:
            raise NotFound("Patient profile is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_status = serializer.validated_data["is_active"]
        if patient.is_active == new_status:
            raise ValidationError({"is_active": "The patient already has this status."})
        previous = patient.is_active
        try:
            with transaction.atomic():
                patient.is_active = new_status
                patient.save(update_fields=("is_active", "updated_at"))
                PatientStatusAudit.objects.create(
                    patient=patient,
                    organization=request.organization,
                    actor=request.user,
                    previous_status=previous,
                    new_status=new_status,
                    reason=serializer.validated_data["reason"],
                )
        except IntegrityError as error:
            raise ValidationError(
                "An active patient with this mobile number already exists."
            ) from error
        return Response(PatientProfileSerializer(patient, context={"request": request}).data)


class PatientPhotoView(PatientTenantMixin, GenericAPIView):
    serializer_class = PatientListSerializer

    def get(self, request, pk):
        patient = self.scoped_queryset().filter(pk=pk).first()
        if patient is None or not patient.profile_photo:
            raise NotFound("Patient photograph is unavailable.")
        return FileResponse(
            patient.profile_photo.open("rb"), content_type="application/octet-stream"
        )


class MyPatientProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    serializer_class = PatientProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_object(self):
        patient = PatientProfile.objects.filter(
            organization=self.request.organization, user=self.request.user, is_active=True
        ).first()
        if patient is None:
            raise NotFound("Patient profile is unavailable.")
        return patient

    def perform_update(self, serializer):
        if "clinic" in serializer.validated_data:
            raise PermissionDenied("Patients cannot change clinic assignment.")
        serializer.save()
