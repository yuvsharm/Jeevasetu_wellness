import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError

from apps.tenancy.models import (
    Clinic,
    ClinicMembership,
    Organization,
    OrganizationMembership,
)


@pytest.fixture
def organizations(db):
    first = Organization.objects.create(
        legal_name="First Legal",
        display_name="First",
        slug="first",
    )
    second = Organization.objects.create(
        legal_name="Second Legal",
        display_name="Second",
        slug="second",
    )
    return first, second


@pytest.mark.django_db
def test_organization_slug_is_unique(organizations):
    with pytest.raises(IntegrityError), transaction.atomic():
        Organization.objects.create(
            legal_name="Duplicate",
            display_name="Duplicate",
            slug=organizations[0].slug,
        )


@pytest.mark.django_db
def test_clinic_slug_is_unique_within_organization(organizations):
    Clinic.objects.create(organization=organizations[0], name="North", slug="north")

    with pytest.raises(IntegrityError), transaction.atomic():
        Clinic.objects.create(organization=organizations[0], name="North Two", slug="north")


@pytest.mark.django_db
def test_same_clinic_slug_is_valid_across_organizations(organizations):
    first = Clinic.objects.create(organization=organizations[0], name="North", slug="north")
    second = Clinic.objects.create(organization=organizations[1], name="North", slug="north")

    assert first.slug == second.slug


@pytest.mark.django_db
def test_organization_membership_is_unique(django_user_model, organizations):
    user = django_user_model.objects.create_user(username="member")
    OrganizationMembership.objects.create(user=user, organization=organizations[0])

    with pytest.raises(IntegrityError), transaction.atomic():
        OrganizationMembership.objects.create(user=user, organization=organizations[0])


@pytest.mark.django_db
def test_clinic_membership_is_unique(django_user_model, organizations):
    user = django_user_model.objects.create_user(username="member")
    membership = OrganizationMembership.objects.create(user=user, organization=organizations[0])
    clinic = Clinic.objects.create(organization=organizations[0], name="North", slug="north")
    ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)

    with pytest.raises(IntegrityError), transaction.atomic():
        ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)


@pytest.mark.django_db
def test_cross_organization_clinic_membership_fails_validation(django_user_model, organizations):
    user = django_user_model.objects.create_user(username="member")
    membership = OrganizationMembership.objects.create(user=user, organization=organizations[0])
    clinic = Clinic.objects.create(organization=organizations[1], name="North", slug="north")

    with pytest.raises(ValidationError):
        ClinicMembership(organization_membership=membership, clinic=clinic).full_clean()


@pytest.mark.django_db
def test_tenant_foreign_keys_are_protected(django_user_model, organizations):
    user = django_user_model.objects.create_user(username="member")
    membership = OrganizationMembership.objects.create(user=user, organization=organizations[0])
    clinic = Clinic.objects.create(organization=organizations[0], name="North", slug="north")
    ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)

    with pytest.raises(ProtectedError):
        organizations[0].delete()
    with pytest.raises(ProtectedError):
        clinic.delete()
    with pytest.raises(ProtectedError):
        membership.delete()
    with pytest.raises(ProtectedError):
        user.delete()


@pytest.mark.django_db
def test_active_querysets_exclude_inactive_tenant_records(django_user_model, organizations):
    active_user = django_user_model.objects.create_user(username="active")
    disabled_user = django_user_model.objects.create_user(username="disabled")
    active_membership = OrganizationMembership.objects.create(
        user=active_user,
        organization=organizations[0],
    )
    OrganizationMembership.objects.create(
        user=disabled_user,
        organization=organizations[0],
        is_active=False,
    )
    active_clinic = Clinic.objects.create(
        organization=organizations[0],
        name="Active",
        slug="active",
    )
    Clinic.objects.create(
        organization=organizations[0],
        name="Inactive",
        slug="inactive",
        is_active=False,
    )

    assert list(Clinic.objects.for_organization(organizations[0]).active()) == [active_clinic]
    assert list(OrganizationMembership.objects.active()) == [active_membership]
    assert not Clinic.objects.for_organization(None).exists()


@pytest.mark.django_db
def test_inactive_organization_excludes_related_active_rows(django_user_model, organizations):
    user = django_user_model.objects.create_user(username="member")
    membership = OrganizationMembership.objects.create(user=user, organization=organizations[0])
    clinic = Clinic.objects.create(organization=organizations[0], name="North", slug="north")
    clinic_membership = ClinicMembership.objects.create(
        organization_membership=membership,
        clinic=clinic,
    )
    organizations[0].is_active = False
    organizations[0].save(update_fields=("is_active", "updated_at"))

    assert not Clinic.objects.active().filter(pk=clinic.pk).exists()
    assert not OrganizationMembership.objects.active().filter(pk=membership.pk).exists()
    assert not ClinicMembership.objects.active().filter(pk=clinic_membership.pk).exists()
