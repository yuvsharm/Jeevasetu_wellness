from django.db.models import Q
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.accounts.models import Role, RoleAssignment
from apps.accounts.permissions import IsEnabledAuthenticated, IsOwnerOrManager, IsPhysiotherapist
from apps.accounts.role_policy import activate_role, actor_role_scope, disable_role
from apps.accounts.services import issue_password_reset
from apps.staff.models import ServiceArea, Specialization, StaffProfile
from apps.staff.serializers import (
    ServiceAreaSerializer,
    SpecializationSerializer,
    StaffCreateSerializer,
    StaffDetailResponseSerializer,
    StaffOptionsSerializer,
    StaffProfileSerializer,
    StaffStatusActionSerializer,
)


class TenantMixin:
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request, "organization", None) is None:
            raise NotFound("Organization context is unavailable.")

    def scoped_queryset(self):
        queryset = (
            StaffProfile.objects.filter(organization=self.request.organization)
            .select_related("user", "clinic")
            .prefetch_related("specializations", "service_areas", "documents")
        )
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        if level == Role.MANAGER:
            queryset = queryset.filter(staff_type=Role.PHYSIOTHERAPIST)
            if clinic_ids is not None:
                queryset = queryset.filter(clinic_id__in=clinic_ids)
        return queryset


class StaffPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 50


class StaffListCreateView(TenantMixin, generics.ListCreateAPIView):
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    pagination_class = StaffPagination

    def get_serializer_class(self):
        return StaffCreateSerializer if self.request.method == "POST" else StaffProfileSerializer

    def get_queryset(self):
        queryset = self.scoped_queryset()
        staff_type = self.request.query_params.get("type", "")
        status_value = self.request.query_params.get("status", "")
        search = self.request.query_params.get("search", "").strip()
        ordering = self.request.query_params.get("ordering", "user__first_name")
        if staff_type:
            queryset = queryset.filter(staff_type=staff_type)
        if status_value in ("active", "inactive"):
            active_ids = RoleAssignment.objects.filter(
                organization=self.request.organization,
                role__in=(Role.MANAGER, Role.PHYSIOTHERAPIST),
                is_active=status_value == "active",
            ).values_list("user_id", flat=True)
            queryset = queryset.filter(user_id__in=active_ids)
        if search:
            queryset = queryset.filter(
                Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(user__email__icontains=search)
                | Q(user__mobile_number__icontains=search)
                | Q(qualification__icontains=search)
            )
        if ordering.lstrip("-") not in (
            "user__first_name",
            "joining_date",
            "experience_years",
            "created_at",
        ):
            ordering = "user__first_name"
        return queryset.order_by(ordering)

    def perform_create(self, serializer):
        level, _ = actor_role_scope(self.request.user, self.request.organization)
        if serializer.validated_data["staff_type"] == Role.MANAGER and level != Role.OWNER:
            raise PermissionDenied("Managers cannot create managers.")
        serializer.save()


class StaffDetailView(TenantMixin, generics.RetrieveUpdateAPIView):
    serializer_class = StaffProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_queryset(self):
        return self.scoped_queryset()


class StaffStatusView(TenantMixin, GenericAPIView):
    serializer_class = StaffStatusActionSerializer

    def post(self, request, pk):
        profile = self.scoped_queryset().filter(pk=pk).first()
        if profile is None:
            raise NotFound("Staff profile is unavailable.")
        assignment = (
            RoleAssignment.objects.filter(
                user=profile.user, organization=request.organization, role=profile.staff_type
            )
            .order_by("-created_at")
            .first()
        )
        if assignment is None:
            raise NotFound("Staff authorization is unavailable.")
        enabled = request.data.get("is_active")
        if enabled is True:
            try:
                activate_role(assignment, actor=request.user)
            except Exception as error:
                raise ValidationError(str(error)) from error
        elif enabled is False and assignment.is_active:
            disable_role(
                assignment,
                actor=request.user,
                reason=request.data.get("reason", "Staff status updated."),
            )
        else:
            raise ValidationError({"is_active": "Provide a boolean status."})
        return Response(StaffProfileSerializer(profile).data)


class ManagerPasswordResetView(TenantMixin, GenericAPIView):
    serializer_class = StaffDetailResponseSerializer

    def post(self, request, pk):
        level, _ = actor_role_scope(request.user, request.organization)
        profile = self.scoped_queryset().filter(pk=pk, staff_type=Role.MANAGER).first()
        if level != Role.OWNER or profile is None:
            raise PermissionDenied("Only an Owner can start a Manager password reset.")
        issue_password_reset(profile.user)
        return Response(
            {"detail": "Password reset was prepared through the secure reset workflow."},
            status=status.HTTP_202_ACCEPTED,
        )


class MyStaffProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    serializer_class = StaffProfileSerializer
    parser_classes = (JSONParser, MultiPartParser, FormParser)

    def get_object(self):
        profile = StaffProfile.objects.filter(
            user=self.request.user,
            organization=self.request.organization,
            staff_type=Role.PHYSIOTHERAPIST,
        ).first()
        if profile is None:
            raise NotFound("Physiotherapist profile is unavailable.")
        return profile


class AvailabilityView(MyStaffProfileView):
    def patch(self, request):
        profile = self.get_object()
        serializer = self.get_serializer(
            profile,
            data={
                key: request.data[key]
                for key in ("availability", "is_online")
                if key in request.data
            },
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StaffOptionsView(TenantMixin, GenericAPIView):
    serializer_class = StaffOptionsSerializer

    def get(self, request):
        return Response(
            {
                "specializations": SpecializationSerializer(
                    Specialization.objects.filter(is_active=True), many=True
                ).data,
                "service_areas": ServiceAreaSerializer(
                    ServiceArea.objects.filter(organization=request.organization, is_active=True),
                    many=True,
                ).data,
            }
        )
