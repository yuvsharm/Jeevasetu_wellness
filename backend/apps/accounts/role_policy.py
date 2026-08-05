from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent
from apps.tenancy.models import Clinic, ClinicMembership, OrganizationMembership

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


def actor_role_scope(actor, organization):
    """Return an actor's active management level and authorized clinic IDs."""
    assignments = RoleAssignment.objects.filter(
        user=actor,
        organization=organization,
        is_active=True,
        organization_membership__is_active=True,
    ).filter(Q(clinic__isnull=True) | Q(clinic__is_active=True, clinic_membership__is_active=True))
    if assignments.filter(role=Role.OWNER, clinic__isnull=True).exists():
        return Role.OWNER, None
    managers = assignments.filter(role=Role.MANAGER)
    if managers.filter(clinic__isnull=True).exists():
        return Role.MANAGER, None
    clinic_ids = set(managers.exclude(clinic__isnull=True).values_list("clinic_id", flat=True))
    if clinic_ids:
        return Role.MANAGER, clinic_ids
    return None, set()


def role_queryset_for_actor(actor, organization):
    """Scope role visibility before object lookup to prevent tenant leakage."""
    base = RoleAssignment.objects.filter(organization=organization).select_related(
        "user", "organization", "clinic"
    )
    level, clinic_ids = actor_role_scope(actor, organization)
    if level == Role.OWNER:
        return base
    if level == Role.MANAGER:
        base = base.filter(role__in=(Role.PHYSIOTHERAPIST, Role.CUSTOMER))
        if clinic_ids is not None:
            base = base.filter(clinic_id__in=clinic_ids)
        return base
    return base.filter(user=actor, is_active=True).filter(
        Q(clinic__isnull=True) | Q(clinic__is_active=True, clinic_membership__is_active=True)
    )


def permitted_clinics_for_actor(actor, organization):
    active_role_clinics = RoleAssignment.objects.filter(
        user=actor,
        organization=organization,
        is_active=True,
        clinic__is_active=True,
        clinic_membership__is_active=True,
    ).values_list("clinic_id", flat=True)
    level, clinic_ids = actor_role_scope(actor, organization)
    if level in (Role.OWNER, Role.MANAGER) and clinic_ids is None:
        return Clinic.objects.active().filter(organization=organization)
    return Clinic.objects.active().filter(organization=organization, id__in=active_role_clinics)


def validate_management_scope(*, actor, target, organization, role, clinic=None):
    validate_role_operation(
        actor=actor, target=target, organization=organization, role=role, clinic=clinic
    )
    level, clinic_ids = actor_role_scope(actor, organization)
    if level == Role.OWNER:
        return
    if level != Role.MANAGER or role not in (Role.PHYSIOTHERAPIST, Role.CUSTOMER):
        record_role_event(
            RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
            actor=actor,
            target=target,
            organization=organization,
            clinic=clinic,
            new_role=role,
        )
        raise PermissionDenied("Role operation is not permitted.")
    if actor == target:
        record_role_event(
            RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
            actor=actor,
            target=target,
            organization=organization,
            clinic=clinic,
            new_role=role,
        )
        raise PermissionDenied("Role operation is not permitted.")
    if clinic_ids is not None and (clinic is None or clinic.id not in clinic_ids):
        record_role_event(
            RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
            actor=actor,
            target=target,
            organization=organization,
            clinic=clinic,
            new_role=role,
        )
        raise PermissionDenied("Role operation is not permitted.")


def resolve_role_memberships(*, target, organization, clinic=None):
    if not target.is_active or not target.is_enabled:
        raise ValidationError("The selected identity cannot receive active authorization.")
    membership = OrganizationMembership.objects.filter(
        user=target, organization=organization, is_active=True
    ).first()
    if membership is None:
        raise ValidationError("The selected identity is unavailable in this organization.")
    clinic_membership = None
    if clinic is not None:
        clinic_membership = ClinicMembership.objects.filter(
            organization_membership=membership, clinic=clinic, is_active=True
        ).first()
        if clinic_membership is None:
            raise ValidationError("An active clinic membership is required.")
    return membership, clinic_membership


def assign_role(*, actor, target, organization, role, clinic=None, request_id=""):
    validate_management_scope(
        actor=actor, target=target, organization=organization, role=role, clinic=clinic
    )
    try:
        membership, clinic_membership = resolve_role_memberships(
            target=target, organization=organization, clinic=clinic
        )
    except ValidationError:
        if not OrganizationMembership.objects.filter(
            user=target, organization=organization
        ).exists():
            record_role_event(
                RoleAuditEvent.Event.CROSS_TENANT,
                actor=actor,
                target=target,
                organization=organization,
                clinic=clinic,
                new_role=role,
                request_id=request_id,
            )
        raise
    value = RoleAssignment(
        user=target,
        role=role,
        organization=organization,
        organization_membership=membership,
        clinic=clinic,
        clinic_membership=clinic_membership,
        assigned_by=actor,
    )
    value.full_clean()
    try:
        with transaction.atomic():
            value.save()
            record_role_event(
                RoleAuditEvent.Event.ASSIGNED,
                actor=actor,
                target=target,
                organization=organization,
                clinic=clinic,
                new_role=role,
                request_id=request_id,
            )
    except IntegrityError as error:
        raise ValidationError("An active assignment already exists.") from error
    return value


def update_role_scope(assignment, *, actor, clinic, request_id=""):
    validate_management_scope(
        actor=actor,
        target=assignment.user,
        organization=assignment.organization,
        role=assignment.role,
        clinic=clinic,
    )
    if assignment.role == Role.OWNER:
        raise ValidationError("Owner scope cannot be changed.")
    membership, clinic_membership = resolve_role_memberships(
        target=assignment.user,
        organization=assignment.organization,
        clinic=clinic,
    )
    assignment.organization_membership = membership
    assignment.clinic = clinic
    assignment.clinic_membership = clinic_membership
    assignment.full_clean()
    try:
        with transaction.atomic():
            assignment.save(
                update_fields=(
                    "organization_membership",
                    "clinic",
                    "clinic_membership",
                    "updated_at",
                )
            )
            record_role_event(
                RoleAuditEvent.Event.CHANGED,
                actor=actor,
                target=assignment.user,
                organization=assignment.organization,
                clinic=clinic,
                old_role=assignment.role,
                new_role=assignment.role,
                request_id=request_id,
                metadata={"change": "clinic_scope"},
            )
    except IntegrityError as error:
        raise ValidationError("An active assignment already exists in this scope.") from error
    return assignment


def activate_role(assignment, *, actor, request_id=""):
    validate_management_scope(
        actor=actor,
        target=assignment.user,
        organization=assignment.organization,
        role=assignment.role,
        clinic=assignment.clinic,
    )
    if assignment.is_active:
        return assignment
    resolve_role_memberships(
        target=assignment.user,
        organization=assignment.organization,
        clinic=assignment.clinic,
    )
    assignment.is_active = True
    assignment.disabled_at = None
    assignment.disabled_reason = ""
    assignment.full_clean()
    try:
        with transaction.atomic():
            assignment.save(
                update_fields=("is_active", "disabled_at", "disabled_reason", "updated_at")
            )
            record_role_event(
                RoleAuditEvent.Event.ACTIVATED,
                actor=actor,
                target=assignment.user,
                organization=assignment.organization,
                clinic=assignment.clinic,
                new_role=assignment.role,
                request_id=request_id,
            )
    except IntegrityError as error:
        raise ValidationError("An active assignment already exists.") from error
    return assignment


def disable_role(assignment, *, actor, reason):
    protected_owner = None
    with transaction.atomic():
        locked = RoleAssignment.objects.select_for_update().get(pk=assignment.pk)
        if locked.role == Role.OWNER and locked.is_active:
            owner_ids = list(
                RoleAssignment.objects.select_for_update()
                .filter(
                    organization=locked.organization,
                    role=Role.OWNER,
                    is_active=True,
                    clinic__isnull=True,
                )
                .order_by("pk")
                .values_list("pk", flat=True)
            )
            if len(owner_ids) <= 1:
                protected_owner = locked
        if protected_owner is None:
            locked.is_active = False
            locked.disabled_at = timezone.now()
            locked.disabled_reason = reason[:255]
            locked.full_clean()
            locked.save(update_fields=("is_active", "disabled_at", "disabled_reason", "updated_at"))
            record_role_event(
                RoleAuditEvent.Event.DISABLED,
                actor=actor,
                target=locked.user,
                organization=locked.organization,
                clinic=locked.clinic,
                old_role=locked.role,
            )
    if protected_owner is not None:
        record_role_event(
            RoleAuditEvent.Event.FINAL_OWNER,
            actor=actor,
            target=protected_owner.user,
            organization=protected_owner.organization,
            old_role=protected_owner.role,
        )
        raise PermissionDenied("An approved ownership transfer is required.")
    return locked
