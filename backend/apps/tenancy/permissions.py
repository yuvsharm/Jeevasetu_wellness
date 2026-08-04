from rest_framework.exceptions import NotAuthenticated, NotFound, ValidationError
from rest_framework.permissions import BasePermission

from apps.tenancy.models import OrganizationMembership


class IsActiveOrganizationMember(BasePermission):
    """Deny by default unless request identity and tenant membership are active."""

    message = "Active organization membership is required."

    def has_permission(self, request, view):
        user = request.user
        if user is None or not user.is_authenticated:
            raise NotAuthenticated()
        if not user.is_active or not user.is_enabled:
            return False
        if request.tenant_resolution == "missing":
            raise ValidationError({"tenant": "Organization context is required."})
        if request.organization is None:
            raise NotFound("Organization context is unavailable.")

        membership = (
            OrganizationMembership.objects.active()
            .filter(user=user, organization=request.organization)
            .first()
        )
        if membership is None:
            return False

        request.organization_membership = membership
        return True
