import json
import io
import logging
import socket
import ssl
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

    def __init__(self, payload=None, *, raw=None):
        self.payload = payload
        self.raw = raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self.raw if self.raw is not None else json.dumps(self.payload).encode()


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


MSG91_VERIFY_URL = "https://api.msg91.com/api/v5/widget/verifyAccessToken"
MSG91 = override_settings(
    MSG91_ENABLED=True,
    MSG91_AUTH_KEY="server-auth-key",
    MSG91_TIMEOUT_SECONDS=0.2,
    MSG91_VERIFY_URL=MSG91_VERIFY_URL,
)


def log_text(caplog):
    return " ".join(record.getMessage() for record in caplog.records)


def assert_sensitive_values_absent(caplog, *values):
    captured = log_text(caplog)
    for value in ("server-auth-key", "browser-access-token", "654321", "9876543210", "919876543210", *values):
        assert value not in captured


@MSG91
def test_msg91_success_uses_server_verification_and_never_discloses_secrets(
    api_client, organization, monkeypatch, caplog
):
    caplog.set_level(logging.INFO, logger="apps.appointments.booking_verification")
    issued = issue(api_client, organization)
    assert issued.status_code == 201
    assert "otp" not in issued.data
    verification = BookingPhoneVerification.objects.get(pk=issued.data["verification_id"])
    assert verification.otp_hash == "msg91-widget"

    captured = {}

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["content_type"] = request.get_header("Content-type")
        captured["accept"] = request.get_header("Accept")
        captured["authkey"] = request.get_header("Authkey")
        captured["timeout"] = timeout
        return Msg91Response({"type": "success", "message": "919876543210"})

    monkeypatch.setattr("apps.appointments.booking_verification.urllib.request.urlopen", urlopen)
    response = verify(api_client, organization, verification.id)
    assert response.status_code == 200
    assert captured == {
        "url": MSG91_VERIFY_URL,
        "method": "POST",
        "body": {"access-token": "browser-access-token"},
        "content_type": "application/json",
        "accept": "application/json",
        "authkey": "server-auth-key",
        "timeout": 0.2,
    }
    assert "authkey" not in captured["body"]
    assert "server-auth-key" not in str(response.data)
    assert "browser-access-token" not in str(response.data)
    assert "msg91_verify_response status=200 provider_type=success message_kind=phone-like keys=message,type" in log_text(caplog)
    assert_sensitive_values_absent(caplog)
    verification.refresh_from_db()
    assert verification.verified_at is not None


@MSG91
@pytest.mark.parametrize(("payload", "expected_error"), [
    ({"type": "error", "message": "invalid token"}, "MSG91 rejected the verification token."),
    ({"type": "success", "message": "verified"}, "Mobile verification does not match this request."),
    ({"type": "success", "message": "919876543211"}, "Mobile verification does not match this request."),
])
def test_msg91_invalid_or_wrong_mobile_fails_closed(
    api_client, organization, monkeypatch, payload, expected_error, caplog
):
    caplog.set_level(logging.INFO, logger="apps.appointments.booking_verification")
    issued = issue(api_client, organization)
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen", lambda *_args, **_kwargs: Msg91Response(payload)
    )
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    assert response.data == [expected_error]
    assert "browser-access-token" not in str(response.data)
    assert "server-auth-key" not in str(response.data)
    assert "919876543211" not in str(response.data)
    value = BookingPhoneVerification.objects.get(pk=issued.data["verification_id"])
    assert value.verified_at is None
    assert value.failed_attempt_count == 1
    if payload["type"] == "error":
        assert "provider_type=error message_kind=status-text" in log_text(caplog)
    assert_sensitive_values_absent(caplog, "invalid token", "919876543211")


@MSG91
@pytest.mark.parametrize("verified_identifier", ["9876543210", "919876543210", "+919876543210"])
def test_msg91_verified_mobile_normalizes_supported_indian_formats(
    api_client, organization, monkeypatch, verified_identifier
):
    issued = issue(api_client, organization)
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen",
        lambda *_args, **_kwargs: Msg91Response({"type": "success", "message": verified_identifier}),
    )
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 200
    assert "token" in response.data


@MSG91
def test_msg91_timeout_fails_closed_without_token_disclosure(api_client, organization, monkeypatch, caplog):
    issued = issue(api_client, organization)

    def timeout(*_args, **_kwargs):
        raise TimeoutError("timed out browser-access-token")

    monkeypatch.setattr("apps.appointments.booking_verification.urllib.request.urlopen", timeout)
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    assert response.data == ["Mobile verification is temporarily unavailable."]
    assert "browser-access-token" not in str(response.data)
    assert "server-auth-key" not in str(response.data)
    assert "msg91_verify_timeout" in log_text(caplog)
    assert_sensitive_values_absent(caplog)


@MSG91
@pytest.mark.parametrize("status", [400, 401, 403, 500])
def test_msg91_http_errors_log_only_safe_classification(
    api_client, organization, monkeypatch, caplog, status
):
    issued = issue(api_client, organization)

    def http_error(*_args, **_kwargs):
        raise urllib.error.HTTPError(
            MSG91_VERIFY_URL,
            status,
            "raw-provider-detail browser-access-token 919876543210",
            None,
            io.BytesIO(b"raw-provider-response server-auth-key 654321"),
        )

    monkeypatch.setattr("apps.appointments.booking_verification.urllib.request.urlopen", http_error)
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    assert response.data == ["Mobile verification is temporarily unavailable."]
    assert f"msg91_verify_http_error status={status} endpoint=api.msg91.com/api/v5/widget/verifyAccessToken" in log_text(caplog)
    assert_sensitive_values_absent(caplog, "raw-provider-detail", "raw-provider-response")


@MSG91
@pytest.mark.parametrize(("reason", "kind"), [
    (socket.gaierror("private-host browser-access-token"), "dns"),
    (ssl.SSLError("private-certificate server-auth-key"), "tls"),
    (ConnectionRefusedError("private-address 919876543210"), "connection"),
    (OSError("private-network-detail 654321"), "other"),
])
def test_msg91_network_errors_log_only_broad_classification(
    api_client, organization, monkeypatch, caplog, reason, kind
):
    issued = issue(api_client, organization)
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(urllib.error.URLError(reason)),
    )
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    assert response.data == ["Mobile verification is temporarily unavailable."]
    assert f"msg91_verify_network_error kind={kind}" in log_text(caplog)
    assert_sensitive_values_absent(
        caplog, "private-host", "private-certificate", "private-address", "private-network-detail"
    )


@MSG91
def test_msg91_invalid_json_logs_no_raw_response(api_client, organization, monkeypatch, caplog):
    issued = issue(api_client, organization)
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen",
        lambda *_args, **_kwargs: Msg91Response(raw=b"raw-provider-response browser-access-token 919876543210"),
    )
    response = verify(api_client, organization, issued.data["verification_id"])
    assert response.status_code == 400
    assert response.data == ["Mobile verification is temporarily unavailable."]
    assert "msg91_verify_invalid_json status=200" in log_text(caplog)
    assert_sensitive_values_absent(caplog, "raw-provider-response")


@MSG91
def test_msg91_customer_login_reuses_customer_session_and_rejects_reuse(api_client, organization, monkeypatch):
    monkeypatch.setattr(
        "apps.appointments.booking_verification.urllib.request.urlopen",
        lambda *_args, **_kwargs: Msg91Response({"type": "success", "data": {"identifier": "919876543210"}}),
    )
    customer = User.objects.create_user(username="customer", mobile_number="+919876543210")
    membership = OrganizationMembership.objects.create(user=customer, organization=organization)
    RoleAssignment.objects.create(
        user=customer,
        organization=organization,
        organization_membership=membership,
        role=Role.CUSTOMER,
    )
    issued = issue(api_client, organization)
    body = {
        "verification_id": issued.data["verification_id"], "mobile_number": "9876543210",
        "access_token": "browser-access-token", "first_name": "Asha",
    }
    logged_in = api_client.post(reverse("auth-customer-otp-login"), body, format="json", **tenant(organization.slug))
    assert logged_in.status_code == 200
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
