from rest_framework.generics import ListAPIView, RetrieveAPIView

from apps.tenancy.models import Clinic
from apps.tenancy.permissions import IsActiveOrganizationMember
from apps.tenancy.serializers import ClinicSerializer, OrganizationContextSerializer


class OrganizationContextView(RetrieveAPIView):
    permission_classes = (IsActiveOrganizationMember,)
    serializer_class = OrganizationContextSerializer

    def get_object(self):
        return self.request.organization


class TenantClinicQuerysetMixin:
    permission_classes = (IsActiveOrganizationMember,)
    serializer_class = ClinicSerializer

    def get_queryset(self):
        return (
            Clinic.objects.for_organization(self.request.organization)
            .active()
            .filter(
                memberships__organization_membership=self.request.organization_membership,
                memberships__is_active=True,
            )
            .distinct()
        )


class ClinicListView(TenantClinicQuerysetMixin, ListAPIView):
    pass


class ClinicDetailView(TenantClinicQuerysetMixin, RetrieveAPIView):
    pass
