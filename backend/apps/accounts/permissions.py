from django.db.models import Q
from rest_framework.permissions import BasePermission

from apps.accounts.models import Role, RoleAssignment


class IsEnabledAuthenticated(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and user.is_active and user.is_enabled)


def active_roles(user, organization, *, clinic=None):
    """Return only fully active assignments in the requested tenant scope."""
    if not user or not user.is_authenticated or not user.is_active or not user.is_enabled:
        return RoleAssignment.objects.none()
    if organization is None or not organization.is_active:
        return RoleAssignment.objects.none()
    roles = RoleAssignment.objects.filter(
        user=user,
        organization=organization,
        is_active=True,
        organization_membership__is_active=True,
        organization_membership__organization__is_active=True,
    ).filter(
        Q(clinic__isnull=True)
        | Q(
            clinic__is_active=True,
            clinic_membership__is_active=True,
            clinic_membership__clinic__is_active=True,
        )
    )
    if clinic is not None:
        if not clinic.is_active or clinic.organization_id != organization.id:
            return RoleAssignment.objects.none()
        roles = roles.filter(
            clinic=clinic,
            clinic_membership__is_active=True,
            clinic_membership__clinic__is_active=True,
        )
    return roles


class HasActiveRole(BasePermission):
    roles = ()

    def has_permission(self, request, view):
        organization = getattr(request, "organization", None)
        clinic = getattr(request, "clinic", None)
        queryset = active_roles(request.user, organization, clinic=clinic)
        if self.roles:
            queryset = queryset.filter(role__in=self.roles)
        return queryset.exists()


class IsOwner(HasActiveRole):
    roles = (Role.OWNER,)


class IsManager(HasActiveRole):
    roles = (Role.MANAGER,)


class IsPhysiotherapist(HasActiveRole):
    roles = (Role.PHYSIOTHERAPIST,)


class IsCustomer(HasActiveRole):
    roles = (Role.CUSTOMER,)


class IsOwnerOrManager(HasActiveRole):
    roles = (Role.OWNER, Role.MANAGER)


class HasOrganizationRole(HasActiveRole):
    def has_permission(self, request, view):
        queryset = active_roles(request.user, getattr(request, "organization", None)).filter(
            clinic__isnull=True
        )
        if self.roles:
            queryset = queryset.filter(role__in=self.roles)
        return queryset.exists()


class HasClinicRole(HasActiveRole):
    def has_permission(self, request, view):
        if getattr(request, "clinic", None) is None:
            return False
        return super().has_permission(request, view)


class IsSelf(BasePermission):
    def has_object_permission(self, request, view, obj):
        object_user = obj if hasattr(obj, "is_authenticated") else getattr(obj, "user", None)
        return bool(request.user.is_authenticated and object_user == request.user)


class IsAssignedObjectUser(BasePermission):
    """Foundation for objects exposing an explicit assigned_user relation."""

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user.is_authenticated and getattr(obj, "assigned_user", None) == request.user
        )
