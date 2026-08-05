from types import SimpleNamespace

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent, User
from apps.accounts.permissions import (
    HasClinicRole,
    HasOrganizationRole,
    IsCustomer,
    IsOwner,
    IsSelf,
)
from apps.accounts.role_policy import disable_role, record_role_event, validate_role_operation
from apps.tenancy.models import (
    Clinic,
    ClinicMembership,
    Organization,
    OrganizationMembership,
)


@pytest.fixture
def tenant(db):
    organization = Organization.objects.create(
        legal_name="Jeeva", display_name="Jeeva", slug="jeeva"
    )
    clinic = Clinic.objects.create(organization=organization, name="North", slug="north")
    return organization, clinic


def member(username, organization, clinic=None):
    user = User.objects.create_user(username=username)
    organization_membership = OrganizationMembership.objects.create(
        user=user, organization=organization
    )
    clinic_membership = None
    if clinic:
        clinic_membership = ClinicMembership.objects.create(
            organization_membership=organization_membership, clinic=clinic
        )
    return user, organization_membership, clinic_membership


def assignment(username, role, organization, clinic=None, *, actor=None):
    user, organization_membership, clinic_membership = member(username, organization, clinic)
    value = RoleAssignment(
        user=user,
        organization=organization,
        organization_membership=organization_membership,
        clinic=clinic,
        clinic_membership=clinic_membership,
        role=role,
        assigned_by=actor,
    )
    value.full_clean()
    value.save()
    return value


def request(user, organization, clinic=None):
    return SimpleNamespace(user=user, organization=organization, clinic=clinic)


@pytest.mark.django_db
def test_only_approved_roles_and_no_default_role(tenant):
    user = User.objects.create_user(username="unassigned")
    assert set(Role.values) == {"OWNER", "MANAGER", "PHYSIOTHERAPIST", "CUSTOMER"}
    assert not user.role_assignments.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "clinic_scoped"),
    [
        (Role.OWNER, False),
        (Role.MANAGER, False),
        (Role.PHYSIOTHERAPIST, True),
        (Role.CUSTOMER, False),
    ],
)
def test_valid_role_assignments(tenant, role, clinic_scoped):
    organization, clinic = tenant
    value = assignment(role.lower(), role, organization, clinic if clinic_scoped else None)
    assert value.is_active


@pytest.mark.django_db
def test_duplicate_active_assignment_prevented_but_disabled_history_allowed(tenant):
    organization, _ = tenant
    first = assignment("manager", Role.MANAGER, organization)
    with pytest.raises(IntegrityError), transaction.atomic():
        RoleAssignment.objects.create(
            user=first.user,
            role=first.role,
            organization=organization,
            organization_membership=first.organization_membership,
        )
    first.is_active = False
    first.disabled_at = timezone.now()
    first.save()
    RoleAssignment.objects.create(
        user=first.user,
        role=first.role,
        organization=organization,
        organization_membership=first.organization_membership,
    )


@pytest.mark.django_db
def test_scope_validation_rejects_mismatches_and_invalid_role_shapes(tenant):
    organization, clinic = tenant
    other = Organization.objects.create(legal_name="Other", display_name="Other", slug="other")
    user, organization_membership, clinic_membership = member("scope", organization, clinic)
    with pytest.raises(ValidationError):
        RoleAssignment(
            user=user,
            role=Role.MANAGER,
            organization=other,
            organization_membership=organization_membership,
        ).full_clean()
    with pytest.raises(ValidationError):
        RoleAssignment(
            user=user,
            role=Role.OWNER,
            organization=organization,
            organization_membership=organization_membership,
            clinic=clinic,
            clinic_membership=clinic_membership,
        ).full_clean()
    with pytest.raises(ValidationError):
        RoleAssignment(
            user=user,
            role=Role.PHYSIOTHERAPIST,
            organization=organization,
            organization_membership=organization_membership,
        ).full_clean()


@pytest.mark.django_db
def test_foreign_keys_are_protected(tenant):
    organization, _ = tenant
    value = assignment("owner", Role.OWNER, organization)
    with pytest.raises(ProtectedError):
        value.organization_membership.delete()


@pytest.mark.django_db
def test_permissions_enforce_tenant_clinic_and_inactive_state(tenant):
    organization, clinic = tenant
    owner = assignment("owner", Role.OWNER, organization)
    physio = assignment("physio", Role.PHYSIOTHERAPIST, organization, clinic)
    assert IsOwner().has_permission(request(owner.user, organization), None)
    assert HasOrganizationRole().has_permission(request(owner.user, organization), None)
    assert HasClinicRole().has_permission(request(physio.user, organization, clinic), None)
    other = Organization.objects.create(legal_name="Other", display_name="Other", slug="other")
    assert not IsOwner().has_permission(request(owner.user, other), None)
    owner.user.is_enabled = False
    owner.user.save()
    assert not IsOwner().has_permission(request(owner.user, organization), None)


@pytest.mark.django_db
@pytest.mark.parametrize("disabled", ["membership", "organization", "clinic", "role"])
def test_disabled_tenant_components_do_not_authorize(tenant, disabled):
    organization, clinic = tenant
    value = assignment(f"disabled-{disabled}", Role.PHYSIOTHERAPIST, organization, clinic)
    obj = {
        "membership": value.organization_membership,
        "organization": organization,
        "clinic": clinic,
        "role": value,
    }[disabled]
    obj.is_active = False
    if disabled == "role":
        obj.disabled_at = timezone.now()
    obj.save()
    assert not HasClinicRole().has_permission(request(value.user, organization, clinic), None)


@pytest.mark.django_db
def test_customer_self_scope_foundation(tenant):
    organization, _ = tenant
    customer = assignment("customer", Role.CUSTOMER, organization)
    other = User.objects.create_user(username="other")
    assert IsCustomer().has_permission(request(customer.user, organization), None)
    assert IsSelf().has_object_permission(request(customer.user, organization), None, customer.user)
    assert not IsSelf().has_object_permission(request(customer.user, organization), None, other)


@pytest.mark.django_db
def test_manager_cannot_assign_owner_or_self_broaden(tenant):
    organization, clinic = tenant
    manager = assignment("manager", Role.MANAGER, organization, clinic)
    target = User.objects.create_user(username="target")
    with pytest.raises(PermissionDenied):
        validate_role_operation(
            actor=manager.user, target=target, organization=organization, role=Role.OWNER
        )
    with pytest.raises(PermissionDenied):
        validate_role_operation(
            actor=manager.user, target=manager.user, organization=organization, role=Role.MANAGER
        )
    assert (
        RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.PRIVILEGE_ESCALATION).count() == 2
    )


@pytest.mark.django_db
def test_cross_tenant_and_platform_role_attempts_are_audited(tenant):
    organization, _ = tenant
    outsider = User.objects.create_user(username="outsider")
    target = User.objects.create_user(username="target")
    with pytest.raises(PermissionDenied):
        validate_role_operation(
            actor=outsider, target=target, organization=organization, role=Role.MANAGER
        )
    with pytest.raises(ValidationError):
        validate_role_operation(
            actor=outsider, target=target, organization=organization, role="SUPER_ADMIN"
        )
    assert set(RoleAuditEvent.objects.values_list("event", flat=True)) == {
        RoleAuditEvent.Event.CROSS_TENANT,
        RoleAuditEvent.Event.PRIVILEGE_ESCALATION,
    }


@pytest.mark.django_db
def test_final_owner_is_protected_and_audited(tenant):
    organization, _ = tenant
    owner = assignment("owner", Role.OWNER, organization)
    with pytest.raises(PermissionDenied):
        disable_role(owner, actor=owner.user, reason="transfer missing")
    owner.refresh_from_db()
    assert owner.is_active
    assert RoleAuditEvent.objects.filter(event=RoleAuditEvent.Event.FINAL_OWNER).exists()


@pytest.mark.django_db
def test_role_audit_is_immutable_and_filters_sensitive_metadata(tenant):
    organization, _ = tenant
    event = record_role_event(
        RoleAuditEvent.Event.ASSIGNED,
        actor=None,
        target=None,
        organization=organization,
        metadata={"reason": "approved", "password": "never-store"},
    )
    assert event.metadata == {"reason": "approved"}
    event.request_id = "changed"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
