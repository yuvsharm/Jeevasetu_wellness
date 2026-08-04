import hashlib
import ipaddress

from apps.accounts.models import AuthenticationAuditEvent


def identifier_digest(identifier):
    if not identifier:
        return ""
    return hashlib.sha256(identifier.strip().lower().encode()).hexdigest()


def client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",", 1)[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def record_auth_event(request, event, outcome, *, user=None, identifier=""):
    return AuthenticationAuditEvent.objects.create(
        event=event,
        outcome=outcome,
        user=user,
        identifier_hash=identifier_digest(identifier),
        ip_address=client_ip(request),
        user_agent=request.META.get("HTTP_USER_AGENT", "")[:255],
    )
