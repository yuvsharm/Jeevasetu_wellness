from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import AppointmentRequest, TherapyOption
from apps.tenancy.models import Organization, OrganizationMembership

pytestmark = pytest.mark.django_db


def setup_identity(role):
    organization = Organization.objects.create(
        legal_name="JeevaSetu",
        display_name="JeevaSetu",
        slug=f"org-{role.lower()}",
        timezone="Asia/Kolkata",
        default_currency="INR",
    )
    user = User.objects.create_user(
        username=f"{role.lower()}user",
        email=f"{role.lower()}@example.com",
        password="Safe-test-password-1",
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    RoleAssignment.objects.create(
        user=user, organization=organization, organization_membership=membership, role=role
    )
    therapy = TherapyOption.objects.create(
        organization=organization, name="Abhyang", slug="abhyang"
    )
    return organization, user, therapy


def payload(therapy):
    return {
        "therapy": str(therapy.id),
        "patient_name": "Asha Sharma",
        "age": 42,
        "gender": "FEMALE",
        "mobile_number": "9876543210",
        "alternate_mobile": "",
        "email": "asha@example.com",
        "session_preference": "SINGLE",
        "preferred_date": str(timezone.localdate() + timedelta(days=2)),
        "preferred_time": "10:00",
        "problem_description": "Persistent lower back discomfort.",
        "pain_area": "Lower back",
        "problem_duration": "Three weeks",
        "doctor_reference": "",
        "address": "163 C Block, Shastri Nagar",
        "city": "Meerut",
        "pin_code": "250004",
        "landmark": "Near community park",
        "google_map_link": "",
    }


def tenant(slug):
    return {"HTTP_X_ORGANIZATION_SLUG": slug}


def test_public_create_validates_and_blocks_duplicate(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    url = reverse("appointment-create")
    first = api_client.post(url, payload(therapy), format="json", **tenant(organization.slug))
    duplicate = api_client.post(url, payload(therapy), format="json", **tenant(organization.slug))
    assert first.status_code == 201
    assert first.data["status"] == "PENDING"
    assert duplicate.status_code == 400
    assert AppointmentRequest.objects.count() == 1


def test_active_therapy_list_is_tenant_scoped(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    TherapyOption.objects.create(
        organization=organization, name="Inactive", slug="inactive", is_active=False
    )
    response = api_client.get(reverse("appointment-therapy-list"), **tenant(organization.slug))
    assert response.status_code == 200
    assert response.data == [{"id": str(therapy.id), "name": "Abhyang", "slug": "abhyang"}]


def test_customer_only_sees_and_cancels_own_pending_request(api_client):
    organization, customer, therapy = setup_identity(Role.CUSTOMER)
    other = User.objects.create_user(
        username="other", email="other@example.com", password="Safe-test-password-1"
    )
    own = AppointmentRequest.objects.create(
        organization=organization,
        creator=customer,
        therapy=therapy,
        **{k: v for k, v in payload(therapy).items() if k != "therapy"},
    )
    hidden = AppointmentRequest.objects.create(
        organization=organization,
        creator=other,
        therapy=therapy,
        **{
            **{k: v for k, v in payload(therapy).items() if k != "therapy"},
            "mobile_number": "9876543211",
        },
    )
    api_client.force_authenticate(customer)
    response = api_client.get(reverse("appointment-mine"), **tenant(organization.slug))
    assert response.status_code == 200
    assert [item["id"] for item in response.data] == [str(own.id)]
    assert (
        api_client.get(
            reverse("appointment-mine-detail", args=[hidden.id]), **tenant(organization.slug)
        ).status_code
        == 404
    )
    cancelled = api_client.patch(
        reverse("appointment-cancel", args=[own.id]), {}, format="json", **tenant(organization.slug)
    )
    assert cancelled.status_code == 200
    own.refresh_from_db()
    assert own.status == AppointmentRequest.Status.CANCELLED


def test_owner_searches_and_updates_tenant_requests(api_client):
    organization, owner, therapy = setup_identity(Role.OWNER)
    request_value = AppointmentRequest.objects.create(
        organization=organization,
        creator=owner,
        therapy=therapy,
        **{k: v for k, v in payload(therapy).items() if k != "therapy"},
    )
    api_client.force_authenticate(owner)
    listed = api_client.get(
        reverse("appointment-owner-list"),
        {"search": "Asha", "status": "PENDING"},
        **tenant(organization.slug),
    )
    assert listed.status_code == 200 and len(listed.data) == 1
    updated = api_client.patch(
        reverse("appointment-owner-detail", args=[request_value.id]),
        {"status": "APPROVED", "owner_remarks": "Confirmed by owner."},
        format="json",
        **tenant(organization.slug),
    )
    assert updated.status_code == 200
    request_value.refresh_from_db()
    assert request_value.status == AppointmentRequest.Status.APPROVED


def test_manager_searches_and_updates_tenant_requests(api_client):
    organization, manager, therapy = setup_identity(Role.MANAGER)
    request_value = AppointmentRequest.objects.create(
        organization=organization,
        creator=manager,
        therapy=therapy,
        **{k: v for k, v in payload(therapy).items() if k != "therapy"},
    )
    api_client.force_authenticate(manager)
    listed = api_client.get(
        reverse("appointment-owner-list"),
        {"search": "Asha", "status": "PENDING"},
        **tenant(organization.slug),
    )
    assert listed.status_code == 200 and len(listed.data) == 1
    updated = api_client.patch(
        reverse("appointment-owner-detail", args=[request_value.id]),
        {"status": "APPROVED", "owner_remarks": "Confirmed by manager."},
        format="json",
        **tenant(organization.slug),
    )
    assert updated.status_code == 200
    request_value.refresh_from_db()
    assert request_value.status == AppointmentRequest.Status.APPROVED


def test_non_owner_cannot_access_owner_queue(api_client):
    organization, customer, _ = setup_identity(Role.CUSTOMER)
    api_client.force_authenticate(customer)
    assert (
        api_client.get(reverse("appointment-owner-list"), **tenant(organization.slug)).status_code
        == 403
    )


def test_server_rejects_past_date_and_cross_tenant_therapy(api_client):
    organization, _, _ = setup_identity(Role.CUSTOMER)
    other_org, _, other_therapy = setup_identity(Role.OWNER)
    invalid = payload(other_therapy)
    invalid["preferred_date"] = str(timezone.localdate() - timedelta(days=1))
    response = api_client.post(
        reverse("appointment-create"), invalid, format="json", **tenant(organization.slug)
    )
    assert response.status_code == 400
    assert "preferred_date" in response.data and "therapy" in response.data
    assert other_org != organization


def test_public_create_accepts_requested_therapies_and_validates_slot(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    secondary = TherapyOption.objects.create(
        organization=organization, name="Kati Basti", slug="kati-basti"
    )
    tertiary = TherapyOption.objects.create(
        organization=organization, name="Nasya", slug="nasya"
    )

    valid = payload(therapy)
    valid["requested_therapies"] = [str(secondary.id), str(tertiary.id)]
    valid["preferred_time"] = "10:00"
    response = api_client.post(
        reverse("appointment-create"), valid, format="json", **tenant(organization.slug)
    )
    assert response.status_code == 201
    request = AppointmentRequest.objects.get(pk=response.data["id"])
    assert set(str(item.id) for item in request.requested_therapies.all()) == {
        str(secondary.id),
        str(tertiary.id),
    }

    invalid = payload(therapy)
    invalid["requested_therapies"] = [str(secondary.id)]
    invalid["preferred_time"] = "19:00"
    invalid_response = api_client.post(
        reverse("appointment-create"), invalid, format="json", **tenant(organization.slug)
    )
    assert invalid_response.status_code == 400
    assert "preferred_time" in invalid_response.data
