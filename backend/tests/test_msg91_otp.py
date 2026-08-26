import json
import urllib.error

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import BookingPhoneVerification
from apps.tenancy.models import Organization, OrganizationMembership

pytestmark = pytest.mark.django_db


class Msg91Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def tenant(slug):
    return {"HTTP_X_ORGANIZATION_SLUG": slug}


@pytest.fixture
def organization():
    return Organization.objects.create(
        legal_name="JeevaSetu", display_name="JeevaSetu", slug="msg91-org", timezone="Asia/Kolkata"
    )


@pytest.fixture(autouse=True)
def reset_cache():
    cache.clear()


def issue(api_client, organization):
    return api_client.post(
        reverse("booking-otp-issue"), {"mobile_number": "9876543210"}, format="json", **tenant(organization.slug)
    )


def verify(api_client, organization, verification_id, access_token="browser-access-token"):
    return api_client.post(
        reverse("booking-otp-verify"),
        {"verification_id": verification_id, "mobile_number": "9876543210", "access_token": access_token},
        format="json", **tenant(organization.slug),
    )


MSG91 = override_settings(MSG91_ENABLED=True, MSG91_AUTH_KEY="server-auth-key", MSG91_TIMEOUT_SECONDS=0.2)


@MSG91
def test_msg91_success_uses_server_verification_and_never_discloses_secrets(api_client, organization, monkeypatch):
    issued = issue(api_client, organization)
    assert issued.status_code == 201
    assert "otp" not in issued.data
    verification = BookingPhoneVerification.objects.get(pk=issued.data["verification_id"])
    assert verification.otp_hash == "msg91-widget"

    captured = {}

    def urlopen(request, timeout):
        captured["body"] = request.data.decode()
        captured["timeout"] = timeout
        return Msg91Response({"type": "success", "message": "verified", "data": {"mobile": "919876543210"}})

    monkeypatch.setattr("apps.appointments.booking_verification.urllib.request.urlopen", urlopen)
    response = verify(api_client, organization, verification.id)
    assert response.status_code == 200
    assert "server-auth-key" in captured["body"]
    assert "browser-access-token" in captured["body"]
    assert "server-auth-key" not in str(response.data)
    assert "browser-access-token" not in str(response.data)
    verification.refresh_from_db()
    assert verification.verified_at is not None


@MSG91
@pytest.mark.parametrize("payload", [
    {"type": "error", "message": "invalid token"},
    {"type": "success", "data": {"mobile": "919876543211"}},
])
def test_msg91_invalid_or_wrong_mobile_fails_closed(api_client, organization, monkeypatch, payload):
    issued = issue(api_client, organization)
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen", lambda *_args, **_kwargs: Msg91Response(payload)
    )
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    value = BookingPhoneVerification.objects.get(pk=issued.data["verification_id"])
    assert value.verified_at is None
    assert value.failed_attempt_count == 1


@MSG91
def test_msg91_timeout_fails_closed_without_token_disclosure(api_client, organization, monkeypatch):
    issued = issue(api_client, organization)

    def timeout(*_args, **_kwargs):
        raise urllib.error.URLError("timed out browser-access-token")

    monkeypatch.setattr("apps.appointments.booking_verification.urllib.request.urlopen", timeout)
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    assert "browser-access-token" not in str(response.data)
    assert "server-auth-key" not in str(response.data)


@MSG91
def test_msg91_customer_login_reuses_customer_session_and_rejects_reuse(api_client, organization, monkeypatch):
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen",
        lambda *_args, **_kwargs: Msg91Response({"type": "success", "data": {"identifier": "919876543210"}}),
    )
    issued = issue(api_client, organization)
    body = {
        "verification_id": issued.data["verification_id"], "mobile_number": "9876543210",
        "access_token": "browser-access-token", "first_name": "Asha",
    }
    logged_in = api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug))
    assert logged_in.status_code == 200
    customer = User.objects.get(mobile_number="+919876543210")
    assert RoleAssignment.objects.filter(user=customer, organization=organization, role=Role.CUSTOMER).exists()
    assert api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug)).status_code == 400


@MSG91
def test_msg91_customer_login_rejects_staff_identity(api_client, organization, monkeypatch):
    staff = User.objects.create_user(username="staff", mobile_number="+919876543210")
    membership = OrganizationMembership.objects.create(user=staff, organization=organization)
    RoleAssignment.objects.create(user=staff, organization=organization, organization_membership=membership, role=Role.OWNER)
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen",
        lambda *_args, **_kwargs: Msg91Response({"type": "success", "data": {"mobile": "919876543210"}}),
    )
    issued = issue(api_client, organization)
    response = api_client.post(
        reverse("auth-customer-otp-login"),
        {"verification_id": issued.data["verification_id"], "mobile_number": "9876543210", "access_token": "token"},
        format="json", **tenant(organization.slug),
    )
    assert response.status_code == 400
    assert BookingPhoneVerification.objects.get(pk=issued.data["verification_id"]).consumed_at is None
