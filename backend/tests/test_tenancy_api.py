import pytest
from django.urls import reverse

from apps.tenancy.models import Clinic, ClinicMembership, Organization, OrganizationMembership

TENANT_HEADER = "HTTP_X_ORGANIZATION_SLUG"


@pytest.fixture
def tenant_data(db, django_user_model):
    first = Organization.objects.create(
        legal_name="First Legal",
        display_name="First Organization",
        slug="first-org",
    )
    second = Organization.objects.create(
        legal_name="Second Legal",
        display_name="Second Organization",
        slug="second-org",
    )
    inactive = Organization.objects.create(
        legal_name="Inactive Legal",
        display_name="Inactive Organization",
        slug="inactive-org",
        is_active=False,
    )
    first_clinic = Clinic.objects.create(organization=first, name="First Clinic", slug="clinic")
    hidden_clinic = Clinic.objects.create(organization=first, name="Hidden Clinic", slug="hidden")
    second_clinic = Clinic.objects.create(organization=second, name="Second Clinic", slug="clinic")
    member = django_user_model.objects.create_user(username="member")
    non_member = django_user_model.objects.create_user(username="outsider")
    disabled_member = django_user_model.objects.create_user(username="disabled")
    first_membership = OrganizationMembership.objects.create(user=member, organization=first)
    OrganizationMembership.objects.create(
        user=disabled_member,
        organization=first,
        is_active=False,
    )
    ClinicMembership.objects.create(
        organization_membership=first_membership,
        clinic=first_clinic,
    )
    return {
        "first": first,
        "second": second,
        "inactive": inactive,
        "first_clinic": first_clinic,
        "hidden_clinic": hidden_clinic,
        "second_clinic": second_clinic,
        "member": member,
        "non_member": non_member,
        "disabled_member": disabled_member,
    }


def authenticate(api_client, user):
    api_client.force_authenticate(user=user)
    return api_client


@pytest.mark.django_db
def test_valid_tenant_member_can_resolve_context(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "first-org"})

    assert response.status_code == 200
    assert response.data["id"] == str(tenant_data["first"].id)
    assert response.data["slug"] == "first-org"


@pytest.mark.django_db
def test_missing_tenant_is_rejected(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(reverse("tenant-context"))

    assert response.status_code == 400
    assert "required" in str(response.data).lower()


@pytest.mark.django_db
@pytest.mark.parametrize("slug", ["unknown-org", "Bad Slug", "../first-org", "first_org"])
def test_invalid_or_malformed_tenant_is_not_disclosed(api_client, tenant_data, slug):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: slug})

    assert response.status_code == 404
    body = str(response.data)
    assert slug not in body
    assert "First Organization" not in body


@pytest.mark.django_db
def test_inactive_tenant_matches_invalid_tenant_response(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    inactive = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "inactive-org"})
    invalid = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "unknown-org"})

    assert inactive.status_code == invalid.status_code == 404
    assert inactive.data == invalid.data


@pytest.mark.django_db
def test_unauthenticated_request_is_denied(api_client, tenant_data):
    response = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "first-org"})

    assert response.status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("user_key", ["disabled_member", "non_member"])
def test_disabled_member_and_non_member_are_denied(api_client, tenant_data, user_key):
    authenticate(api_client, tenant_data[user_key])

    response = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "first-org"})

    assert response.status_code == 403


@pytest.mark.django_db
def test_cross_organization_access_is_denied(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "second-org"})

    assert response.status_code == 403
    assert "Second Organization" not in str(response.data)


@pytest.mark.django_db
def test_clinic_list_contains_only_active_mapped_clinics(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(reverse("tenant-clinic-list"), **{TENANT_HEADER: "first-org"})

    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [str(tenant_data["first_clinic"].id)]


@pytest.mark.django_db
def test_cross_clinic_direct_object_access_is_not_found(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(
        reverse("tenant-clinic-detail", args=(tenant_data["hidden_clinic"].id,)),
        **{TENANT_HEADER: "first-org"},
    )

    assert response.status_code == 404
    assert "Hidden Clinic" not in str(response.data)


@pytest.mark.django_db
def test_cross_organization_direct_object_access_is_not_found(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(
        reverse("tenant-clinic-detail", args=(tenant_data["second_clinic"].id,)),
        **{TENANT_HEADER: "first-org"},
    )

    assert response.status_code == 404
    assert "Second Clinic" not in str(response.data)


@pytest.mark.django_db
def test_object_identifier_cannot_bypass_missing_tenant(api_client, tenant_data):
    authenticate(api_client, tenant_data["member"])

    response = api_client.get(
        reverse("tenant-clinic-detail", args=(tenant_data["first_clinic"].id,))
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_request_user_path_is_authenticator_agnostic(api_client, tenant_data):
    """force_authenticate exercises the same request.user contract future JWT uses."""

    authenticate(api_client, tenant_data["member"])
    response = api_client.get(reverse("tenant-context"), **{TENANT_HEADER: "first-org"})

    assert response.status_code == 200
