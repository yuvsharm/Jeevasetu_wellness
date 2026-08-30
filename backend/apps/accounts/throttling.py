from rest_framework.throttling import SimpleRateThrottle


class CustomerRegistrationRateThrottle(SimpleRateThrottle):
    """Limit final customer creation per tenant and originating client IP."""

    scope = "customer_register"

    def get_cache_key(self, request, view):
        organization = getattr(request, "organization", None)
        organization_key = str(organization.pk) if organization is not None else "unknown"
        ident = self.get_ident(request)
        return self.cache_format % {
            "scope": f"{self.scope}:{organization_key}",
            "ident": ident,
        }
