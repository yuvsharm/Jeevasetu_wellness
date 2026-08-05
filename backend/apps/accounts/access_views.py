from django.core.exceptions import (
    PermissionDenied as DjangoPermissionDenied,
)
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
)
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.access_serializers import (
    AccessRoleSerializer,
    AccessSummarySerializer,
    RoleActionSerializer,
    RoleCreateSerializer,
    RoleDeactivateSerializer,
    RoleUpdateSerializer,
)
from apps.accounts.models import RoleAssignment, RoleAuditEvent
from apps.accounts.permissions import HasActiveRole, IsEnabledAuthenticated, active_roles
from apps.accounts.role_policy import (
    activate_role,
    disable_role,
    permitted_clinics_for_actor,
    record_role_event,
    role_queryset_for_actor,
    validate_management_scope,
)
from apps.tenancy.permissions import IsActiveOrganizationMember

TENANT_PARAMETER = OpenApiParameter(
    name="X-Organization-Slug",
    type=str,
    location=OpenApiParameter.HEADER,
    required=True,
    description="Active organization context for this JWT-authenticated request.",
)
ACCESS_ERRORS = {
    401: OpenApiResponse(description="JWT authentication is required."),
    403: OpenApiResponse(description="The active identity or role scope is not authorized."),
    404: OpenApiResponse(description="The tenant or role assignment is unavailable."),
}
VALIDATION_ERROR = OpenApiResponse(description="The request failed safe field validation.")
ACCESS_SUMMARY_EXAMPLE = OpenApiExample(
    "Safe access summary",
    value={
        "user_id": "11111111-1111-4111-8111-111111111111",
        "organization": {
            "id": "22222222-2222-4222-8222-222222222222",
            "slug": "jeevasetu",
        },
        "permitted_clinics": [{"id": "33333333-3333-4333-8333-333333333333", "slug": "north"}],
        "roles": [],
    },
    response_only=True,
    status_codes=["200"],
)
ROLE_CREATE_EXAMPLE = OpenApiExample(
    "Assign a clinic role",
    value={
        "user_id": "11111111-1111-4111-8111-111111111111",
        "role": "PHYSIOTHERAPIST",
        "clinic_id": "33333333-3333-4333-8333-333333333333",
    },
    request_only=True,
)


class AccessPermissionMixin:
    permission_classes = (IsEnabledAuthenticated, IsActiveOrganizationMember, HasActiveRole)

    def request_id(self):
        return self.request.headers.get("X-Request-ID", "")[:64]


class AccessSummaryView(AccessPermissionMixin, APIView):
    @extend_schema(
        parameters=[TENANT_PARAMETER],
        responses={200: AccessSummarySerializer, **ACCESS_ERRORS},
        examples=[ACCESS_SUMMARY_EXAMPLE],
        description="Return only the caller's active access in the selected organization.",
    )
    def get(self, request):
        roles = active_roles(request.user, request.organization).select_related(
            "user", "organization", "clinic"
        )
        payload = {
            "user_id": request.user.id,
            "organization": request.organization,
            "permitted_clinics": permitted_clinics_for_actor(request.user, request.organization),
            "roles": roles,
        }
        return Response(AccessSummarySerializer(payload).data)


class RoleCollectionView(AccessPermissionMixin, GenericAPIView):
    serializer_class = AccessRoleSerializer

    def get_queryset(self):
        return role_queryset_for_actor(self.request.user, self.request.organization).order_by(
            "role", "created_at"
        )

    @extend_schema(
        parameters=[TENANT_PARAMETER],
        responses={200: AccessRoleSerializer(many=True), **ACCESS_ERRORS},
        description="List role assignments visible within the caller's authorized scope.",
    )
    def get(self, request):
        return Response(AccessRoleSerializer(self.get_queryset(), many=True).data)

    @extend_schema(
        parameters=[TENANT_PARAMETER],
        request=RoleCreateSerializer,
        responses={201: AccessRoleSerializer, 400: VALIDATION_ERROR, **ACCESS_ERRORS},
        examples=[ROLE_CREATE_EXAMPLE],
        description="Assign a role within Owner or delegated Manager boundaries.",
    )
    def post(self, request):
        serializer = RoleCreateSerializer(
            data=request.data,
            context={
                "request": request,
                "organization": request.organization,
                "request_id": self.request_id(),
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            assignment = serializer.save()
        except DjangoPermissionDenied as error:
            raise PermissionDenied(str(error)) from error
        return Response(AccessRoleSerializer(assignment).data, status=status.HTTP_201_CREATED)


class RoleObjectMixin(AccessPermissionMixin):
    def get_assignment(self):
        assignment = (
            role_queryset_for_actor(self.request.user, self.request.organization)
            .filter(pk=self.kwargs["pk"])
            .first()
        )
        if assignment is None:
            hidden = RoleAssignment.objects.filter(pk=self.kwargs["pk"]).first()
            if hidden is not None:
                record_role_event(
                    (
                        RoleAuditEvent.Event.CROSS_TENANT
                        if hidden.organization_id != self.request.organization.id
                        else RoleAuditEvent.Event.PRIVILEGE_ESCALATION
                    ),
                    actor=self.request.user,
                    target=(
                        hidden.user
                        if hidden.organization_id == self.request.organization.id
                        else None
                    ),
                    organization=self.request.organization,
                    request_id=self.request_id(),
                )
            from rest_framework.exceptions import NotFound

            raise NotFound("Role assignment is unavailable.")
        return assignment


class RoleDetailView(RoleObjectMixin, GenericAPIView):
    serializer_class = AccessRoleSerializer

    @extend_schema(
        parameters=[TENANT_PARAMETER],
        responses={200: AccessRoleSerializer, **ACCESS_ERRORS},
    )
    def get(self, request, pk):
        return Response(AccessRoleSerializer(self.get_assignment()).data)

    @extend_schema(
        parameters=[TENANT_PARAMETER],
        request=RoleUpdateSerializer,
        responses={200: AccessRoleSerializer, 400: VALIDATION_ERROR, **ACCESS_ERRORS},
        description="Correct clinic scope; role, user, and organization are immutable.",
    )
    def patch(self, request, pk):
        assignment = self.get_assignment()
        serializer = RoleUpdateSerializer(
            assignment,
            data=request.data,
            partial=True,
            context={
                "request": request,
                "organization": request.organization,
                "request_id": self.request_id(),
            },
        )
        serializer.is_valid(raise_exception=True)
        try:
            assignment = serializer.save()
        except DjangoPermissionDenied as error:
            raise PermissionDenied(str(error)) from error
        return Response(AccessRoleSerializer(assignment).data)


class RoleActivateView(RoleObjectMixin, GenericAPIView):
    @extend_schema(
        parameters=[TENANT_PARAMETER],
        request=RoleActionSerializer,
        responses={200: AccessRoleSerializer, 400: VALIDATION_ERROR, **ACCESS_ERRORS},
        description="Activate an assignment idempotently after revalidating its scope.",
    )
    def post(self, request, pk):
        serializer = RoleActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = self.get_assignment()
        try:
            assignment = activate_role(assignment, actor=request.user, request_id=self.request_id())
        except DjangoPermissionDenied as error:
            raise PermissionDenied(str(error)) from error
        except DjangoValidationError as error:
            raise ValidationError(error.messages) from error
        return Response(AccessRoleSerializer(assignment).data)


class RoleDeactivateView(RoleObjectMixin, GenericAPIView):
    @extend_schema(
        parameters=[TENANT_PARAMETER],
        request=RoleDeactivateSerializer,
        responses={200: AccessRoleSerializer, 400: VALIDATION_ERROR, **ACCESS_ERRORS},
        description="Deactivate an assignment without deleting its audit history.",
    )
    def post(self, request, pk):
        serializer = RoleDeactivateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        assignment = self.get_assignment()
        try:
            validate_management_scope(
                actor=request.user,
                target=assignment.user,
                organization=assignment.organization,
                role=assignment.role,
                clinic=assignment.clinic,
            )
            if assignment.is_active:
                assignment = disable_role(
                    assignment,
                    actor=request.user,
                    reason=serializer.validated_data["reason"],
                )
        except DjangoPermissionDenied as error:
            raise PermissionDenied(str(error)) from error
        return Response(AccessRoleSerializer(assignment).data)
