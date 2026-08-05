from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent

SENSITIVE_METADATA_KEYS = {
    "password",
    "token",
    "jwt",
    "refresh",
    "otp",
    "authorization",
    "clinical_information",
    "therapy_protocol",
}


def record_role_event(
    event,
    *,
    actor,
    target,
    organization,
    clinic=None,
    old_role="",
    new_role="",
    request_id="",
    metadata=None,
):
    safe_metadata = {
        str(key)[:64]: value
        for key, value in (metadata or {}).items()
        if str(key).lower() not in SENSITIVE_METADATA_KEYS
    }
    return RoleAuditEvent.objects.create(
        event=event,
        acting_user=actor,
        target_user=target,
        organization=organization,
        clinic=clinic,
        old_role=old_role,
        new_role=new_role,
        request_id=request_id[:64],
        metadata=safe_metadata,
    )


def validate_role_operation(*, actor, target, organization, role, clinic=None):
    if role not in Role.values:
        record_role_event(
            RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
            actor=actor,
            target=target,
            organization=organization,
            new_role=str(role)[:32],
        )
        raise ValidationError("Unsupported role.")
    actor_roles = RoleAssignment.objects.filter(
        user=actor,
        organization=organization,
        is_active=True,
        organization_membership__is_active=True,
    )
    if not actor_roles.exists():
        record_role_event(
            RoleAuditEvent.Event.CROSS_TENANT,
            actor=actor,
            target=target,
            organization=organization,
            clinic=clinic,
            new_role=role,
        )
        raise PermissionDenied("Role operation is not permitted.")
    is_owner = actor_roles.filter(role=Role.OWNER, clinic__isnull=True).exists()
    if role == Role.OWNER and not is_owner:
        record_role_event(
            RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
            actor=actor,
            target=target,
            organization=organization,
            clinic=clinic,
            new_role=role,
        )
        raise PermissionDenied("Role operation is not permitted.")
    if actor == target and clinic is None and not is_owner:
        record_role_event(
            RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
            actor=actor,
            target=target,
            organization=organization,
            new_role=role,
        )
        raise PermissionDenied("Role operation is not permitted.")


def disable_role(assignment, *, actor, reason):
    protected_owner = None
    with transaction.atomic():
        locked = RoleAssignment.objects.select_for_update().get(pk=assignment.pk)
        if locked.role == Role.OWNER and locked.is_active:
            owners = RoleAssignment.objects.filter(
                organization=locked.organization,
                role=Role.OWNER,
                is_active=True,
                clinic__isnull=True,
            ).count()
            if owners <= 1:
                protected_owner = locked
        if protected_owner is None:
            locked.is_active = False
            locked.disabled_at = timezone.now()
            locked.disabled_reason = reason[:255]
            locked.full_clean()
            locked.save(update_fields=("is_active", "disabled_at", "disabled_reason", "updated_at"))
    if protected_owner is not None:
        record_role_event(
            RoleAuditEvent.Event.FINAL_OWNER,
            actor=actor,
            target=protected_owner.user,
            organization=protected_owner.organization,
            old_role=protected_owner.role,
        )
        raise PermissionDenied("An approved ownership transfer is required.")
    record_role_event(
        RoleAuditEvent.Event.DISABLED,
        actor=actor,
        target=locked.user,
        organization=locked.organization,
        clinic=locked.clinic,
        old_role=locked.role,
    )
    return locked
