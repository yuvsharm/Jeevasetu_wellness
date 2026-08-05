import pytest
from django.core.management import CommandError, call_command
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent, User
from apps.tenancy.models import (
    Clinic,
    ClinicMembership,
    Organization,
    OrganizationMembership,
)

EMAIL = "owner@example.com"


@pytest.mark.django_db
def test_bootstrap_creates_minimum_owner_tenant_data(capsys):
    user = User.objects.create_user(username="first-owner", email=EMAIL)

    call_command("bootstrap_jeevasetu_owner", email=EMAIL)

    organization = Organization.objects.get(slug="jeevasetu-wellness")
    clinic = Clinic.objects.get(organization=organization, slug="meerut")
    membership = OrganizationMembership.objects.get(user=user, organization=organization)
    clinic_membership = ClinicMembership.objects.get(
        organization_membership=membership,
        clinic=clinic,
    )
    assignment = RoleAssignment.objects.get(
        user=user,
        organization=organization,
        role=Role.OWNER,
        is_active=True,
    )

    assert organization.display_name == organization.legal_name == "JeevaSetu Wellness"
    assert organization.timezone == clinic.timezone == "Asia/Kolkata"
    assert organization.default_currency == "INR"
    assert organization.is_active and clinic.is_active
    assert membership.is_active and clinic_membership.is_active
    assert assignment.organization_membership == membership
    assert assignment.clinic_id is None and assignment.clinic_membership_id is None
    assert assignment.assigned_by_id is None
    assert RoleAuditEvent.objects.filter(
        event=RoleAuditEvent.Event.ASSIGNED,
        target_user=user,
        organization=organization,
        new_role=Role.OWNER,
        metadata={"source": "bootstrap_jeevasetu_owner"},
    ).exists()
    assert "created=5" in capsys.readouterr().out


@pytest.mark.django_db
def test_bootstrap_second_run_is_idempotent(capsys):
    User.objects.create_user(username="first-owner", email=EMAIL)
    call_command("bootstrap_jeevasetu_owner", email=EMAIL)
    identifiers = {
        "organization": Organization.objects.get().pk,
        "clinic": Clinic.objects.get().pk,
        "organization_membership": OrganizationMembership.objects.get().pk,
        "clinic_membership": ClinicMembership.objects.get().pk,
        "role": RoleAssignment.objects.get().pk,
    }
    capsys.readouterr()

    call_command("bootstrap_jeevasetu_owner", email=EMAIL.upper())

    assert Organization.objects.get().pk == identifiers["organization"]
    assert Clinic.objects.get().pk == identifiers["clinic"]
    assert OrganizationMembership.objects.get().pk == identifiers["organization_membership"]
    assert ClinicMembership.objects.get().pk == identifiers["clinic_membership"]
    assert RoleAssignment.objects.get().pk == identifiers["role"]
    assert RoleAuditEvent.objects.count() == 1
    assert "created=0, updated=0" in capsys.readouterr().out


@pytest.mark.django_db
def test_bootstrap_requires_an_existing_active_user():
    with pytest.raises(CommandError, match="No registered user exists"):
        call_command("bootstrap_jeevasetu_owner", email=EMAIL)
    assert not Organization.objects.exists()

    user = User.objects.create_user(username="disabled", email=EMAIL, is_enabled=False)
    with pytest.raises(CommandError, match="must be active and enabled"):
        call_command("bootstrap_jeevasetu_owner", email=EMAIL)
    assert user.pk and not Organization.objects.exists()


@pytest.mark.django_db
def test_bootstrap_reactivates_existing_records_and_audits_owner_activation():
    User.objects.create_user(username="first-owner", email=EMAIL)
    call_command("bootstrap_jeevasetu_owner", email=EMAIL)
    assignment = RoleAssignment.objects.get()
    assignment.is_active = False
    assignment.disabled_at = timezone.now()
    assignment.disabled_reason = "development test"
    assignment.save()
    Organization.objects.update(is_active=False)
    Clinic.objects.update(is_active=False)
    OrganizationMembership.objects.update(is_active=False)
    ClinicMembership.objects.update(is_active=False)

    call_command("bootstrap_jeevasetu_owner", email=EMAIL)

    assignment.refresh_from_db()
    assert assignment.is_active
    assert assignment.disabled_at is None and assignment.disabled_reason == ""
    assert Organization.objects.get().is_active
    assert Clinic.objects.get().is_active
    assert OrganizationMembership.objects.get().is_active
    assert ClinicMembership.objects.get().is_active
    assert set(RoleAuditEvent.objects.values_list("event", flat=True)) == {
        RoleAuditEvent.Event.ASSIGNED,
        RoleAuditEvent.Event.ACTIVATED,
    }
