from datetime import time

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import ClinicOperatingHours
from apps.tenancy.models import Clinic, Organization, OrganizationMembership

pytestmark = pytest.mark.django_db
LOCAL_OTP = override_settings(MSG91_ENABLED=False)


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()


@pytest.fixture
def organization():
    organization = Organization.objects.create(legal_name="JeevaSetu", display_name="JeevaSetu", slug="password-auth", timezone="Asia/Kolkata", default_currency="INR")
    clinic = Clinic.objects.create(organization=organization, name="Main", slug="main", timezone="Asia/Kolkata")
    ClinicOperatingHours.objects.create(clinic=clinic, weekdays=list(range(7)), opens_at=time(9), closes_at=time(18))
    return organization


def tenant(organization):
    return {"HTTP_X_ORGANIZATION_SLUG": organization.slug}


def customer(organization, mobile="9876543210", password="Original-Password-2026!"):
    user = User.objects.create_user(username=None, mobile_number=f"+91{mobile}", password=password)
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    RoleAssignment.objects.create(user=user, organization=organization, organization_membership=membership, role=Role.CUSTOMER)
    return user


def issue(api_client, organization, mobile="9876543210"):
    return api_client.post(reverse("booking-otp-issue"), {"mobile_number": mobile}, format="json", **tenant(organization))


def login(api_client, organization, mobile="9876543210", password="Original-Password-2026!"):
    return api_client.post(reverse("auth-customer-login"), {"mobile_number": mobile, "password": password}, format="json", **tenant(organization))


def test_customer_password_login_and_fixed_seven_day_refresh(api_client, organization):
    customer(organization)
    response = login(api_client, organization)
    assert response.status_code == 200
    refresh = RefreshToken(response.data["refresh"])
    assert response.data["refresh_max_age"] == 604800
    assert refresh["customer_session"] is True
    assert refresh["exp"] - refresh["iat"] == 604800
    refreshed = api_client.post(reverse("auth-refresh"), {"refresh": response.data["refresh"]}, format="json")
    assert refreshed.status_code == 200
    assert refreshed.data["refresh"] == response.data["refresh"]
    assert 0 < refreshed.data["refresh_max_age"] <= 604800


def test_customer_login_is_generic_for_wrong_unknown_and_staff(api_client, organization):
    customer(organization)
    wrong = login(api_client, organization, password="wrong")
    unknown = login(api_client, organization, mobile="9876543211")
    staff = User.objects.create_user(username=None, mobile_number="+919876543212", password="Original-Password-2026!")
    membership = OrganizationMembership.objects.create(user=staff, organization=organization)
    RoleAssignment.objects.create(user=staff, organization=organization, organization_membership=membership, role=Role.MANAGER)
    staff_result = login(api_client, organization, mobile="9876543212")
    assert [wrong.status_code, unknown.status_code, staff_result.status_code] == [401, 401, 401]
    assert wrong.data == unknown.data == staff_result.data == {"detail": "Invalid mobile number or password."}


@LOCAL_OTP
def test_customer_password_reset_consumes_otp_changes_password_and_revokes_sessions(api_client, organization):
    user = customer(organization)
    signed_in = login(api_client, organization)
    issued = issue(api_client, organization)
    payload = {"verification_id": issued.data["verification_id"], "mobile_number": "9876543210", "otp": issued.data["otp"], "new_password": "Replacement-Password-2026!", "confirm_password": "Replacement-Password-2026!"}
    reset = api_client.post(reverse("auth-customer-password-reset"), payload, format="json", **tenant(organization))
    assert reset.status_code == 200
    user.refresh_from_db()
    assert user.check_password("Replacement-Password-2026!")
    assert BlacklistedToken.objects.filter(token__user=user).exists()
    assert login(api_client, organization).status_code == 401
    assert login(api_client, organization, password="Replacement-Password-2026!").status_code == 200
    assert api_client.post(reverse("auth-customer-password-reset"), payload, format="json", **tenant(organization)).status_code == 400
    assert api_client.post(reverse("auth-refresh"), {"refresh": signed_in.data["refresh"]}, format="json").status_code == 401


@LOCAL_OTP
def test_reset_rejects_wrong_otp_and_password_mismatch(api_client, organization):
    customer(organization)
    issued = issue(api_client, organization)
    base = {"verification_id": issued.data["verification_id"], "mobile_number": "9876543210", "otp": "000000" if issued.data["otp"] != "000000" else "111111", "new_password": "Replacement-Password-2026!", "confirm_password": "Replacement-Password-2026!"}
    assert api_client.post(reverse("auth-customer-password-reset"), base, format="json", **tenant(organization)).status_code == 400
    base.update(otp=issued.data["otp"], confirm_password="different")
    mismatch = api_client.post(reverse("auth-customer-password-reset"), base, format="json", **tenant(organization))
    assert mismatch.status_code == 400
    assert "confirm_password" in mismatch.data
