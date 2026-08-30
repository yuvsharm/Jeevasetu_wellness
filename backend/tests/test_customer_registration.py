from datetime import time

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory
from rest_framework.throttling import ScopedRateThrottle

from apps.accounts.models import Role, RoleAssignment, User
from apps.accounts.throttling import CustomerRegistrationRateThrottle
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


def verify(api_client, organization, issued, otp=None, mobile="9876543210"):
    return api_client.post(
        reverse("booking-otp-verify"),
        {"verification_id": issued.data["verification_id"], "mobile_number": mobile,
         "otp": otp if otp is not None else issued.data["otp"]},
        format="json", **tenant(organization),
    )


def registration_payload(token, mobile="9876543210", **overrides):
    payload = {
        "booking_verification_token": token,
        "mobile_number": mobile,
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
    payload.update(overrides)
    return payload


@LOCAL_OTP
def test_customer_registration_requires_verification_then_creates_profile_and_session(api_client, organization):
    issued = issue(api_client, organization)
    wrong = "000000" if issued.data["otp"] != "000000" else "111111"
    rejected = verify(api_client, organization, issued, wrong)
    assert rejected.status_code == 400
    assert not User.objects.filter(mobile_number="+919876543210").exists()

    verified = verify(api_client, organization, issued)
    assert verified.status_code == 200
    completed = api_client.post(
        reverse("auth-customer-register"), registration_payload(verified.data["token"]),
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
    verified = verify(api_client, organization, issued)
    duplicate = api_client.post(
        reverse("auth-customer-register"), registration_payload(verified.data["token"]),
        format="json", **tenant(organization),
    )
    assert duplicate.status_code == 400
    assert duplicate.data == {
        "mobile_number": "This mobile number is already registered. Please sign in."
    }

    cache.clear()
    staff_mobile = "9876543211"
    staff = User.objects.create_user(username="owner", mobile_number=f"+91{staff_mobile}")
    staff_membership = OrganizationMembership.objects.create(user=staff, organization=organization)
    RoleAssignment.objects.create(
        user=staff, organization=organization, organization_membership=staff_membership, role=Role.OWNER
    )
    staff_issued = issue(api_client, organization, staff_mobile)
    staff_verified = verify(api_client, organization, staff_issued, mobile=staff_mobile)
    rejected = api_client.post(
        reverse("auth-customer-register"), registration_payload(staff_verified.data["token"], mobile=staff_mobile),
        format="json", **tenant(organization),
    )
    assert rejected.status_code == 400
    assert rejected.data == {
        "mobile_number": "Staff accounts must use the staff sign-in flow."
    }
    assert not RoleAssignment.objects.filter(user=staff, role=Role.CUSTOMER).exists()


@LOCAL_OTP
def test_registration_proof_is_mobile_bound_unexpired_and_single_use(api_client, organization):
    issued = issue(api_client, organization)
    token = verify(api_client, organization, issued).data["token"]
    tampered = api_client.post(
        reverse("auth-customer-register"), registration_payload(token, mobile="9876543211"),
        format="json", **tenant(organization),
    )
    assert tampered.status_code == 400
    assert "verification_proof" in tampered.data
    assert not User.objects.filter(mobile_number="+919876543211").exists()

    BookingPhoneVerification.objects.filter(pk=issued.data["verification_id"]).update(
        expires_at=timezone.now()
    )
    expired = api_client.post(
        reverse("auth-customer-register"), registration_payload(token),
        format="json", **tenant(organization),
    )
    assert expired.status_code == 400
    assert expired.data == {"verification_proof": ["Please verify your mobile number again."]}
    assert not User.objects.filter(mobile_number="+919876543210").exists()

    cache.clear()
    fresh = issue(api_client, organization, mobile="9876543212")
    fresh_token = verify(api_client, organization, fresh, mobile="9876543212").data["token"]
    created = api_client.post(
        reverse("auth-customer-register"), registration_payload(fresh_token, mobile="9876543212"),
        format="json", **tenant(organization),
    )
    assert created.status_code == 201
    reused = api_client.post(
        reverse("auth-customer-register"), registration_payload(fresh_token, mobile="9876543212"),
        format="json", **tenant(organization),
    )
    assert reused.status_code == 400
    assert User.objects.filter(mobile_number="+919876543212").count() == 1


@LOCAL_OTP
def test_registration_proof_is_bound_to_organization(api_client, organization):
    issued = issue(api_client, organization)
    token = verify(api_client, organization, issued).data["token"]
    other = Organization.objects.create(
        legal_name="Other", display_name="Other", slug="other-proof-tenant",
        timezone="Asia/Kolkata", default_currency="INR",
    )
    Clinic.objects.create(organization=other, name="Other Clinic", slug="other")
    response = api_client.post(
        reverse("auth-customer-register"), registration_payload(token),
        format="json", **tenant(other),
    )
    assert response.status_code == 400
    assert response.data == {"verification_proof": ["Mobile verification does not match this booking."]}
    assert not User.objects.filter(mobile_number="+919876543210").exists()


@LOCAL_OTP
def test_registration_password_confirmation_and_django_validation(api_client, organization):
    issued = issue(api_client, organization)
    token = verify(api_client, organization, issued).data["token"]
    mismatch = api_client.post(
        reverse("auth-customer-register"),
        registration_payload(token, confirm_password="different"),
        format="json", **tenant(organization),
    )
    assert mismatch.status_code == 400 and "confirm_password" in mismatch.data
    weak = api_client.post(
        reverse("auth-customer-register"),
        registration_payload(token, password="password", confirm_password="password"),
        format="json", **tenant(organization),
    )
    assert weak.status_code == 400
    serialized_error = str(weak.data)
    assert token not in serialized_error
    assert "string='password'" not in serialized_error
    assert not User.objects.filter(mobile_number="+919876543210").exists()


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


def test_customer_registration_throttle_is_tenant_and_ip_scoped(organization):
    factory = APIRequestFactory()
    first = factory.post("/api/v1/auth/customer-register/", {}, REMOTE_ADDR="192.0.2.10")
    first.organization = organization
    same = factory.post("/api/v1/auth/customer-register/", {}, REMOTE_ADDR="192.0.2.10")
    same.organization = organization
    other_ip = factory.post("/api/v1/auth/customer-register/", {}, REMOTE_ADDR="192.0.2.11")
    other_ip.organization = organization
    other_tenant = Organization.objects.create(
        legal_name="Other", display_name="Other", slug="other-registration",
        timezone="Asia/Kolkata", default_currency="INR",
    )
    other = factory.post("/api/v1/auth/customer-register/", {}, REMOTE_ADDR="192.0.2.10")
    other.organization = other_tenant
    throttle = CustomerRegistrationRateThrottle()
    assert throttle.get_cache_key(first, None) == throttle.get_cache_key(same, None)
    assert throttle.get_cache_key(first, None) != throttle.get_cache_key(other_ip, None)
    assert throttle.get_cache_key(first, None) != throttle.get_cache_key(other, None)


def test_customer_registration_throttle_limit_retry_and_expiry(api_client, organization, monkeypatch):
    monkeypatch.setitem(CustomerRegistrationRateThrottle.THROTTLE_RATES, "customer_register", "1/minute")
    clock = [1_000.0]
    monkeypatch.setattr(CustomerRegistrationRateThrottle, "timer", staticmethod(lambda: clock[0]))
    url = reverse("auth-customer-register")
    first = api_client.post(url, {}, format="json", **tenant(organization))
    limited = api_client.post(url, {}, format="json", **tenant(organization))
    assert first.status_code == 400
    assert limited.status_code == 429
    assert 1 <= limited.data["retry_after"] <= 60
    assert limited.headers["Retry-After"] == str(limited.data["retry_after"])
    assert "Too many registration attempts" in str(limited.data["detail"])
    clock[0] += 61
    assert api_client.post(url, {}, format="json", **tenant(organization)).status_code == 400


def test_customer_registration_does_not_inherit_generic_registration_lockout(api_client, organization, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "auth_register", "1/hour")
    monkeypatch.setitem(CustomerRegistrationRateThrottle.THROTTLE_RATES, "customer_register", "5/hour")
    generic = reverse("auth-register")
    assert api_client.post(generic, {}, format="json").status_code == 400
    assert api_client.post(generic, {}, format="json").status_code == 429
    assert api_client.post(
        reverse("auth-customer-register"), {}, format="json", **tenant(organization)
    ).status_code == 400


def test_development_customer_registration_rate_is_practical():
    assert settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["customer_register"] == "30/hour"
