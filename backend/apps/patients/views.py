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
from apps.accounts.permissions import IsCustomer, IsEnabledAuthenticated, IsOwnerOrManager
from apps.accounts.role_policy import actor_role_scope
from apps.patients.models import CustomerFamilyMember, PatientProfile, PatientStatusAudit
from apps.patients.serializers import (
    CustomerMobileChangeSerializer,
    CustomerPhotoSerializer,
    CustomerSelfProfileSerializer,
    CustomerSelfProfileUpdateSerializer,
    PatientListSerializer,
    PatientProfileSerializer,
    PatientStatusSerializer,
    CustomerFamilyMemberSerializer,
)


class CustomerFamilyMemberListCreateView(generics.ListCreateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerFamilyMemberSerializer

    def get_queryset(self):
        return CustomerFamilyMember.objects.filter(
            organization=self.request.organization, customer=self.request.user, is_active=True
        )

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization, customer=self.request.user)


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


class MyPatientProfileView(GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_object(self):
        patient = PatientProfile.objects.filter(
            organization=self.request.organization, user=self.request.user, is_active=True
        ).first()
        if patient is None:
            raise NotFound("Patient profile is unavailable.")
        return patient

    def get(self, request):
        return Response(CustomerSelfProfileSerializer(self.get_object()).data)

    @transaction.atomic
    def patch(self, request):
        patient = self.get_object()
        if "mobile_number" in request.data:
            raise ValidationError({"mobile_number": "Use Change Mobile with OTP verification."})
        serializer = CustomerSelfProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = patient.user
        for field in ("first_name", "last_name", "email"):
            if field in data:
                setattr(user, field, data[field])
        user.full_clean(exclude=("password",))
        user.save(update_fields=("first_name", "last_name", "email"))
        patient.full_name = f"{user.first_name} {user.last_name}".strip()
        patient.email = user.email
        for field in ("gender", "date_of_birth"):
            if field in data:
                setattr(patient, field, data[field])
        patient.save()
        address_fields = (
            "address_line_1", "address_line_2", "landmark", "city", "region", "pin_code"
        )
        if any(field in data for field in address_fields):
            address = patient.addresses.filter(is_active=True, is_primary=True).first()
            if address is None:
                raise ValidationError({"address": "Primary address is unavailable."})
            for field in address_fields:
                if field in data:
                    setattr(address, field, data[field])
            address.full_clean()
            address.save()
        return Response(CustomerSelfProfileSerializer(patient).data)


class MyPatientPhotoView(GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    parser_classes = (MultiPartParser, FormParser)

    def patient(self):
        value = PatientProfile.objects.filter(
            organization=self.request.organization, user=self.request.user, is_active=True
        ).first()
        if value is None:
            raise NotFound("Patient profile is unavailable.")
        return value

    def get(self, request):
        patient = self.patient()
        if not patient.profile_photo:
            raise NotFound("Patient photograph is unavailable.")
        return FileResponse(patient.profile_photo.open("rb"), content_type="application/octet-stream")

    def post(self, request):
        serializer = CustomerPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        patient = self.patient()
        if patient.profile_photo:
            patient.profile_photo.delete(save=False)
        patient.profile_photo = serializer.validated_data["profile_photo"]
        patient.save(update_fields=("profile_photo", "updated_at"))
        return Response(CustomerSelfProfileSerializer(patient).data)

    def delete(self, request):
        patient = self.patient()
        if patient.profile_photo:
            patient.profile_photo.delete(save=False)
            patient.profile_photo = ""
            patient.save(update_fields=("profile_photo", "updated_at"))
        return Response(status=204)


class MyPatientMobileView(GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsCustomer)
    serializer_class = CustomerMobileChangeSerializer

    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        from apps.accounts.models import User
        from apps.appointments.booking_verification import resolve_booking_verification
        try:
            proof = resolve_booking_verification(
                organization=request.organization,
                mobile_number=data["mobile_number"],
                token=data["booking_verification_token"],
                lock=True,
            )
        except Exception as error:
            raise ValidationError(getattr(error, "messages", [str(error)])) from error
        normalized = f"+91{data['mobile_number']}"
        if User.objects.exclude(pk=request.user.pk).filter(mobile_number=normalized).exists():
            raise ValidationError({"mobile_number": "This mobile number is already registered."})
        patient = PatientProfile.objects.select_for_update().get(
            organization=request.organization, user=request.user, is_active=True
        )
        previous = patient.mobile_number
        request.user.mobile_number = normalized
        request.user.save(update_fields=("mobile_number",))
        patient.mobile_number = data["mobile_number"]
        if (
            patient.emergency_contact_relationship == "Self"
            and patient.emergency_contact_mobile == previous
        ):
            patient.emergency_contact_mobile = data["mobile_number"]
        patient.save()
        from django.utils import timezone
        proof.consumed_at = timezone.now()
        proof.save(update_fields=("consumed_at",))
        return Response(CustomerSelfProfileSerializer(patient).data)
