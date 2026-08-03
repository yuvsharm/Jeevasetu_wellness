import re

from apps.tenancy.models import Organization

TENANT_HEADER = "HTTP_X_ORGANIZATION_SLUG"
TENANT_SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class TenantContextMiddleware:
    """Resolve an optional request-scoped tenant without authorizing access."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.organization = None
        request.tenant_resolution = "missing"
        slug = request.META.get(TENANT_HEADER, "")

        if slug:
            if len(slug) > 63 or TENANT_SLUG_PATTERN.fullmatch(slug) is None:
                request.tenant_resolution = "unavailable"
            else:
                organization = Organization.objects.filter(slug=slug).first()
                if organization is not None and organization.is_active:
                    request.organization = organization
                    request.tenant_resolution = "resolved"
                else:
                    request.tenant_resolution = "unavailable"

        return self.get_response(request)
