import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models import Role, RoleAssignment, User
from apps.tenancy.models import Clinic, Organization

EXPECTED_ROLES = {
    "SUPER_ADMIN",
    "ORGANIZATION_ADMIN",
    "CLINIC_ADMIN",
    "RECEPTION",
    "THERAPIST",
    "AYURVEDA_DOCTOR",
    "YOGA_TRAINER",
    "HOMECARE_EXECUTIVE",
    "PATIENT",
}


@pytest.mark.django_db
def test_required_role_constants_exist_without_permissions():
    assert set(Role.values) == EXPECTED_ROLES


@pytest.mark.django_db
def test_role_assignment_is_unique_per_scope():
    user = User.objects.create_user(username="role-user")
    RoleAssignment.objects.create(user=user, role=Role.SUPER_ADMIN)

    with pytest.raises(IntegrityError), transaction.atomic():
        RoleAssignment.objects.create(user=user, role=Role.SUPER_ADMIN)


@pytest.mark.django_db
def test_clinic_role_must_match_organization():
    user = User.objects.create_user(username="role-user")
    first = Organization.objects.create(legal_name="First", display_name="First", slug="first")
    second = Organization.objects.create(legal_name="Second", display_name="Second", slug="second")
    clinic = Clinic.objects.create(organization=first, name="Clinic", slug="clinic")

    with pytest.raises(ValidationError):
        RoleAssignment(
            user=user,
            role=Role.CLINIC_ADMIN,
            organization=second,
            clinic=clinic,
        ).full_clean()
