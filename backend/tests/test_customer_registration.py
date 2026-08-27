from datetime import time

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import BookingPhoneVerification, ClinicOperatingHours
from apps.patients.models import PatientAddress, PatientProfile
from apps.tenancy.models import Clinic, Organization, OrganizationMembership

pytestmark = pytest.mark.django_db
LOCAL_OTP = override_settings(MSG91_ENABLED=False)


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()


@pytest.fixture
def organization():
    value = Organization.objects.create(
        legal_name="JeevaSetu", display_name="JeevaSetu", slug="customer-registration",
        timezone="Asia/Kolkata", default_currency="INR",
    )
    clinic = Clinic.objects.create(
        organization=value, name="Main Clinic", slug="main", timezone="Asia/Kolkata"
    )
    ClinicOperatingHours.objects.create(
        clinic=clinic, weekdays=list(range(7)), opens_at=time(9), closes_at=time(18)
    )
    return value


def tenant(organization):
    return {"HTTP_X_ORGANIZATION_SLUG": organization.slug}


def issue(api_client, organization, mobile="9876543210"):
    return api_client.post(
        reverse("booking-otp-issue"), {"mobile_number": mobile}, format="json", **tenant(organization)
    )


def registration_payload(issued, otp=None, mobile="9876543210"):
    return {
        "verification_id": issued.data["verification_id"],
        "mobile_number": mobile,
        "otp": otp if otp is not None else issued.data["otp"],
        "full_name": "Asha Sharma",
        "email": "asha@example.com",
        "password": "Asha-Strong-Password-2026!",
        "confirm_password": "Asha-Strong-Password-2026!",
        "age": 34,
        "gender": "FEMALE",
        "address": {
            "address_line_1": "163 C Block",
            "address_line_2": "Shastri Nagar",
            "landmark": "Community park",
            "city": "Meerut",
            "region": "Uttar Pradesh",
            "pin_code": "250004",
        },
    }


@LOCAL_OTP
def test_customer_registration_requires_verification_then_creates_profile_and_session(api_client, organization):
    issued = issue(api_client, organization)
    wrong = "000000" if issued.data["otp"] != "000000" else "111111"
    rejected = api_client.post(
        reverse("auth-customer-register"), registration_payload(issued, wrong),
        format="json", **tenant(organization),
    )
    assert rejected.status_code == 400
    assert not User.objects.filter(mobile_number="+919876543210").exists()

    completed = api_client.post(
        reverse("auth-customer-register"), registration_payload(issued),
        format="json", **tenant(organization),
    )
    assert completed.status_code == 201
    assert set(completed.data) == {"access", "refresh", "refresh_max_age", "user"}
    customer = User.objects.get(mobile_number="+919876543210")
    assert customer.check_password("Asha-Strong-Password-2026!")
    assert customer.email == "asha@example.com"
    assert completed.data["refresh_max_age"] == 7 * 24 * 60 * 60
    assert RoleAssignment.objects.filter(
        user=customer, organization=organization, role=Role.CUSTOMER, is_active=True
    ).exists()
    profile = PatientProfile.objects.get(user=customer, organization=organization)
    assert profile.full_name == "Asha Sharma" and profile.age == 34
    assert PatientAddress.objects.filter(patient=profile, is_primary=True, is_active=True).exists()
    verification = BookingPhoneVerification.objects.get(pk=issued.data["verification_id"])
    assert verification.verified_at is not None and verification.consumed_at is not None


@LOCAL_OTP
def test_customer_registration_rejects_duplicate_and_staff_mobile(api_client, organization):
    existing = User.objects.create_user(username="existing", mobile_number="+919876543210")
    membership = OrganizationMembership.objects.create(user=existing, organization=organization)
    RoleAssignment.objects.create(
        user=existing, organization=organization, organization_membership=membership, role=Role.CUSTOMER
    )
    issued = issue(api_client, organization)
    duplicate = api_client.post(
        reverse("auth-customer-register"), registration_payload(issued),
        format="json", **tenant(organization),
    )
    assert duplicate.status_code == 400
    assert "already registered" in str(duplicate.data).lower()

    cache.clear()
    staff_mobile = "9876543211"
    staff = User.objects.create_user(username="owner", mobile_number=f"+91{staff_mobile}")
    staff_membership = OrganizationMembership.objects.create(user=staff, organization=organization)
    RoleAssignment.objects.create(
        user=staff, organization=organization, organization_membership=staff_membership, role=Role.OWNER
    )
    staff_issued = issue(api_client, organization, staff_mobile)
    rejected = api_client.post(
        reverse("auth-customer-register"), registration_payload(staff_issued, mobile=staff_mobile),
        format="json", **tenant(organization),
    )
    assert rejected.status_code == 400
    assert rejected.data == ["Staff accounts must use the staff sign-in flow."]
    assert not RoleAssignment.objects.filter(user=staff, role=Role.CUSTOMER).exists()


@LOCAL_OTP
def test_customer_login_never_registers_an_unknown_mobile(api_client, organization):
    issued = issue(api_client, organization)
    response = api_client.post(
        reverse("auth-customer-otp-login"),
        {
            "verification_id": issued.data["verification_id"],
            "mobile_number": "9876543210",
            "otp": issued.data["otp"],
        },
        format="json", **tenant(organization),
    )
    assert response.status_code == 400
    assert response.data == ["Register as a customer before signing in."]
    assert not User.objects.filter(mobile_number="+919876543210").exists()
