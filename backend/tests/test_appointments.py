from datetime import timedelta

import pytest
from django.core.cache import cache
from django.core.signing import dumps
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.booking_verification import TOKEN_SALT
from apps.appointments.models import AppointmentRequest, BookingPhoneVerification, TherapyOption
from apps.tenancy.models import Organization, OrganizationMembership
from apps.patients.models import CustomerFamilyMember

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


def issue_and_verify(api_client, organization, mobile_number="9876543210"):
    headers = tenant(organization.slug)
    issued = api_client.post(
        reverse("booking-otp-issue"),
        {"mobile_number": mobile_number},
        format="json",
        **headers,
    )
    assert issued.status_code == 201
    wrong_otp = "000000" if issued.data["otp"] != "000000" else "111111"
    rejected = api_client.post(
        reverse("booking-otp-verify"),
        {
            "verification_id": issued.data["verification_id"],
            "mobile_number": mobile_number,
            "otp": wrong_otp,
        },
        format="json",
        **headers,
    )
    assert rejected.status_code == 400
    rejected_verification = BookingPhoneVerification.objects.get(pk=issued.data["verification_id"])
    assert rejected_verification.failed_attempt_count == 1
    verified = api_client.post(
        reverse("booking-otp-verify"),
        {
            "verification_id": issued.data["verification_id"],
            "mobile_number": mobile_number,
            "otp": issued.data["otp"],
        },
        format="json",
        **headers,
    )
    assert verified.status_code == 200
    return BookingPhoneVerification.objects.get(pk=issued.data["verification_id"]), verified.data["token"]


def test_quick_booking_requires_verified_mobile_and_consumes_token(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    secondary = TherapyOption.objects.create(
        organization=organization, name="Kati Basti", slug="kati-basti"
    )
    url = reverse("quick-appointment-create")
    headers = tenant(organization.slug)
    data = payload(therapy)
    data["requested_therapies"] = [str(therapy.id), str(secondary.id)]

    missing = api_client.post(url, data, format="json", **headers)
    assert missing.status_code == 400
    assert "booking_verification_token" in missing.data

    verification, token = issue_and_verify(api_client, organization)
    wrong_mobile = {**data, "mobile_number": "9876543211", "booking_verification_token": token}
    assert api_client.post(url, wrong_mobile, format="json", **headers).status_code == 400

    data["booking_verification_token"] = token
    created = api_client.post(url, data, format="json", **headers)
    assert created.status_code == 201
    assert created.data["status"] == "PENDING"
    request_value = AppointmentRequest.objects.get(pk=created.data["id"])
    assert request_value.patient_name == "Asha Sharma"
    assert request_value.age == 42
    assert request_value.gender == "FEMALE"
    assert request_value.mobile_number == "9876543210"
    assert str(request_value.preferred_date) == data["preferred_date"]
    assert request_value.preferred_time.strftime("%H:%M") == data["preferred_time"]
    assert set(request_value.requested_therapies.values_list("id", flat=True)) == {secondary.id}
    verification.refresh_from_db()
    assert verification.consumed_at is not None
    assert api_client.post(url, data, format="json", **headers).status_code == 400


def test_quick_booking_rejects_unverified_and_expired_verification(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    headers = tenant(organization.slug)
    url = reverse("quick-appointment-create")
    data = payload(therapy)
    unverified = BookingPhoneVerification.objects.create(
        organization=organization,
        mobile_number=data["mobile_number"],
        otp_hash="not-used",
        expires_at=timezone.now() + timedelta(minutes=5),
    )
    data["booking_verification_token"] = dumps(
        {
            "verification_id": str(unverified.id),
            "mobile_number": data["mobile_number"],
            "organization_id": str(organization.id),
        },
        salt=TOKEN_SALT,
        compress=True,
    )
    assert api_client.post(url, data, format="json", **headers).status_code == 400
    verification, token = issue_and_verify(api_client, organization, "9876543212")
    verification.expires_at = timezone.now() - timedelta(seconds=1)
    verification.save(update_fields=("expires_at",))
    data.update(mobile_number="9876543212", booking_verification_token=token)
    assert api_client.post(url, data, format="json", **headers).status_code == 400


def test_customer_otp_login_creates_normal_customer_session_and_cannot_be_reused(api_client):
    organization, _, _ = setup_identity(Role.OWNER)
    issued = api_client.post(reverse("booking-otp-issue"), {"mobile_number": "9876543210"}, format="json", **tenant(organization.slug))
    body = {"verification_id": issued.data["verification_id"], "mobile_number": "9876543210", "otp": issued.data["otp"], "first_name": "Asha"}
    logged_in = api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug))
    assert logged_in.status_code == 200
    customer = User.objects.get(mobile_number="+919876543210")
    assert RoleAssignment.objects.filter(user=customer, organization=organization, role=Role.CUSTOMER, is_active=True).exists()
    assert BookingPhoneVerification.objects.get(pk=issued.data["verification_id"]).consumed_at is not None
    assert api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug)).status_code == 400


def test_multi_therapy_duration_and_closing_time_are_enforced(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    second = TherapyOption.objects.create(organization=organization, name="Nasya", slug="nasya")
    verification, token = issue_and_verify(api_client, organization)
    data = payload(therapy) | {"requested_therapies": [str(second.id)], "preferred_time": "16:30", "booking_verification_token": token}
    created = api_client.post(reverse("quick-appointment-create"), data, format="json", **tenant(organization.slug))
    assert created.status_code == 201
    assert created.data["requested_duration_minutes"] == 90
    cache.clear()
    _, later_token = issue_and_verify(api_client, organization)
    data |= {"preferred_time": "17:00", "booking_verification_token": later_token}
    assert api_client.post(reverse("quick-appointment-create"), data, format="json", **tenant(organization.slug)).status_code == 400


def test_customer_cannot_book_for_another_customers_family_member(api_client):
    organization, owner, therapy = setup_identity(Role.CUSTOMER)
    other = User.objects.create_user(username="other-customer", password="Safe-test-password-1")
    other_membership = OrganizationMembership.objects.create(user=other, organization=organization)
    RoleAssignment.objects.create(user=other, organization=organization, organization_membership=other_membership, role=Role.CUSTOMER)
    family = CustomerFamilyMember.objects.create(organization=organization, customer=other, full_name="Other Family", age=30, gender="OTHER", relationship="Sibling")
    api_client.force_authenticate(owner)
    data = payload(therapy) | {"family_member": str(family.id)}
    response = api_client.post(reverse("appointment-create"), data, format="json", **tenant(organization.slug))
    assert response.status_code == 400
    assert "family_member" in response.data

def test_failed_quick_booking_does_not_consume_verification(api_client):
    organization, _, therapy = setup_identity(Role.CUSTOMER)
    verification, token = issue_and_verify(api_client, organization)
    data = payload(therapy)
    data.update(preferred_time="19:00", booking_verification_token=token)
    response = api_client.post(
        reverse("quick-appointment-create"),
        data,
        format="json",
        **tenant(organization.slug),
    )
    assert response.status_code == 400
    verification.refresh_from_db()
    assert verification.consumed_at is None


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
