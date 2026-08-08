from datetime import timedelta

import pytest
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import AuthenticationAuditEvent, PasswordResetRequest, User
from apps.tenancy.models import Organization, OrganizationMembership

PASSWORD = "Str0ng!FoundationPass"
NEW_PASSWORD = "An0ther!FoundationPass"


@pytest.fixture(autouse=True)
def reset_throttle_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="identity-user",
        email="identity@example.com",
        mobile_number="+919876543210",
        password=PASSWORD,
        first_name="Identity",
        last_name="User",
    )


def registration_payload(**overrides):
    payload = {
        "first_name": "New",
        "last_name": "User",
        "mobile_number": "+91 98765 43211",
        "email": " New.User@Example.COM ",
        "password": PASSWORD,
        "confirm_password": PASSWORD,
    }
    payload.update(overrides)
    return payload


def login(api_client, identifier="identity@example.com", password=PASSWORD):
    return api_client.post(
        reverse("auth-login"),
        {"identifier": identifier, "password": password},
        format="json",
    )


def authorize(api_client, access):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return api_client


@pytest.mark.django_db
def test_registration_normalizes_identity_and_hashes_password(api_client):
    response = api_client.post(reverse("auth-register"), registration_payload(), format="json")

    assert response.status_code == 201
    user = User.objects.get(pk=response.data["id"])
    assert user.email == "new.user@example.com"
    assert user.mobile_number == "+919876543211"
    assert user.check_password(PASSWORD)
    assert user.username.startswith("user-")
    assert "password" not in response.data
    assert AuthenticationAuditEvent.objects.filter(
        event=AuthenticationAuditEvent.Event.REGISTRATION,
        outcome=AuthenticationAuditEvent.Outcome.SUCCESS,
        user=user,
    ).exists()


@pytest.mark.django_db
def test_registration_creates_tenant_membership_without_a_role(api_client):
    organization = Organization.objects.create(
        legal_name="JeevaSetu", display_name="JeevaSetu", slug="applicant-registration"
    )

    response = api_client.post(
        reverse("auth-register"),
        registration_payload(),
        format="json",
        HTTP_X_ORGANIZATION_SLUG=organization.slug,
    )

    user = User.objects.get(pk=response.data["id"])
    assert response.status_code == 201
    assert OrganizationMembership.objects.filter(user=user, organization=organization).exists()
    assert not user.role_assignments.exists()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("field", "value"),
    [("email", "IDENTITY@EXAMPLE.COM"), ("mobile_number", "+91 98765-43210")],
)
def test_registration_rejects_duplicate_normalized_identity(api_client, user, field, value):
    response = api_client.post(
        reverse("auth-register"), registration_payload(**{field: value}), format="json"
    )

    assert response.status_code == 400
    assert field in response.data


@pytest.mark.django_db
@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "weak", "confirm_password": "weak"},
        {"confirm_password": "Different!FoundationPass1"},
        {"mobile_number": "9876543210"},
    ],
)
def test_registration_rejects_invalid_credentials(api_client, overrides):
    response = api_client.post(
        reverse("auth-register"), registration_payload(**overrides), format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_registration_requires_at_least_one_login_identifier(api_client):
    response = api_client.post(
        reverse("auth-register"),
        registration_payload(email="", mobile_number=None),
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("identifier", ["identity@example.com", "+91 98765 43210"])
def test_login_supports_email_and_mobile(api_client, user, identifier):
    response = login(api_client, identifier)

    assert response.status_code == 200
    assert response.data["access"]
    assert response.data["refresh"]
    assert response.data["user"]["id"] == str(user.id)
    assert response.data["user"]["email"] == user.email
    assert AuthenticationAuditEvent.objects.filter(
        event=AuthenticationAuditEvent.Event.LOGIN,
        outcome=AuthenticationAuditEvent.Outcome.SUCCESS,
        user=user,
    ).exists()


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["invalid", "inactive", "disabled"])
def test_login_rejects_invalid_inactive_and_disabled_users(api_client, user, state):
    if state == "inactive":
        user.is_active = False
        user.save(update_fields=("is_active",))
    elif state == "disabled":
        user.is_enabled = False
        user.save(update_fields=("is_enabled",))
    password = "wrong" if state == "invalid" else PASSWORD

    response = login(api_client, password=password)

    assert response.status_code == 401
    assert response.data["detail"] == "Invalid credentials."
    assert AuthenticationAuditEvent.objects.filter(
        event=AuthenticationAuditEvent.Event.LOGIN,
        outcome=AuthenticationAuditEvent.Outcome.FAILURE,
    ).exists()


@pytest.mark.django_db
def test_access_token_authenticates_profile(api_client, user):
    tokens = login(api_client).data
    response = authorize(api_client, tokens["access"]).get(reverse("auth-profile"))

    assert response.status_code == 200
    assert response.data["id"] == str(user.id)


@pytest.mark.django_db
def test_expired_access_token_is_rejected(api_client, user):
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=timedelta(seconds=-1))

    response = authorize(api_client, str(token)).get(reverse("auth-profile"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_refresh_rotates_and_blacklists_submitted_token(api_client, user):
    original = login(api_client).data["refresh"]
    original_jti = RefreshToken(original)["jti"]

    response = api_client.post(reverse("auth-refresh"), {"refresh": original}, format="json")

    assert response.status_code == 200
    assert response.data["refresh"] != original
    assert response.data["access"]
    assert BlacklistedToken.objects.filter(token__jti=original_jti).exists()
    replay = api_client.post(reverse("auth-refresh"), {"refresh": original}, format="json")
    assert replay.status_code == 401


@pytest.mark.django_db
@pytest.mark.parametrize("state", ["inactive", "disabled"])
def test_refresh_rejects_inactive_and_disabled_users(api_client, user, state):
    refresh = login(api_client).data["refresh"]
    setattr(user, "is_active" if state == "inactive" else "is_enabled", False)
    user.save(update_fields=("is_active" if state == "inactive" else "is_enabled",))

    response = api_client.post(reverse("auth-refresh"), {"refresh": refresh}, format="json")

    assert response.status_code == 401
    assert response.data["detail"] == "Refresh token is invalid or expired."


@pytest.mark.django_db
def test_logout_blacklists_refresh_token(api_client, user):
    tokens = login(api_client).data
    authorize(api_client, tokens["access"])

    response = api_client.post(
        reverse("auth-logout"), {"refresh": tokens["refresh"]}, format="json"
    )

    assert response.status_code == 204
    api_client.credentials()
    replay = api_client.post(reverse("auth-refresh"), {"refresh": tokens["refresh"]}, format="json")
    assert replay.status_code == 401


@pytest.mark.django_db
def test_logout_rejects_another_users_refresh(api_client, user):
    tokens = login(api_client).data
    other = User.objects.create_user(
        username="other",
        email="other@example.com",
        mobile_number="+919876543299",
        password=PASSWORD,
    )
    authorize(api_client, str(RefreshToken.for_user(other).access_token))

    response = api_client.post(
        reverse("auth-logout"), {"refresh": tokens["refresh"]}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_password_change_requires_old_password_and_revokes_tokens(api_client, user):
    tokens = login(api_client).data
    authorize(api_client, tokens["access"])
    invalid = api_client.post(
        reverse("auth-password-change"),
        {
            "old_password": "wrong",
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
        format="json",
    )
    assert invalid.status_code == 400

    response = api_client.post(
        reverse("auth-password-change"),
        {
            "old_password": PASSWORD,
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert authorize(api_client, tokens["access"]).get(reverse("auth-profile")).status_code == 401
    api_client.credentials()
    assert login(api_client, password=NEW_PASSWORD).status_code == 200


@pytest.mark.django_db
def test_password_reset_is_single_use_and_stores_only_digest(api_client, user, settings):
    settings.AUTH_EXPOSE_PASSWORD_RESET_TOKEN = True
    response = api_client.post(
        reverse("auth-password-reset-request"), {"identifier": user.email}, format="json"
    )

    assert response.status_code == 202
    reset = PasswordResetRequest.objects.get(user=user)
    assert response.data["token"] not in reset.token_digest
    payload = {
        "uid": response.data["uid"],
        "token": response.data["token"],
        "new_password": NEW_PASSWORD,
        "confirm_password": NEW_PASSWORD,
    }
    completed = api_client.post(reverse("auth-password-reset-confirm"), payload, format="json")
    replay = api_client.post(reverse("auth-password-reset-confirm"), payload, format="json")

    assert completed.status_code == 200
    assert replay.status_code == 400
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


@pytest.mark.django_db
def test_expired_password_reset_is_rejected(api_client, user, settings):
    settings.AUTH_EXPOSE_PASSWORD_RESET_TOKEN = True
    issued = api_client.post(
        reverse("auth-password-reset-request"), {"identifier": user.email}, format="json"
    ).data
    PasswordResetRequest.objects.filter(user=user).update(expires_at=timezone.now())

    response = api_client.post(
        reverse("auth-password-reset-confirm"),
        {
            "uid": issued["uid"],
            "token": issued["token"],
            "new_password": NEW_PASSWORD,
            "confirm_password": NEW_PASSWORD,
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_password_reset_request_does_not_disclose_unknown_identity(api_client):
    response = api_client.post(
        reverse("auth-password-reset-request"),
        {"identifier": "unknown@example.com"},
        format="json",
    )

    assert response.status_code == 202
    assert "token" not in response.data
    event = AuthenticationAuditEvent.objects.get(
        event=AuthenticationAuditEvent.Event.PASSWORD_RESET_REQUEST
    )
    assert event.user is None
    assert event.identifier_hash
    assert "unknown@example.com" not in event.identifier_hash


@pytest.mark.django_db
def test_profile_update_normalizes_identity_and_records_audit(api_client, user):
    tokens = login(api_client).data
    authorize(api_client, tokens["access"])

    response = api_client.patch(
        reverse("auth-profile"),
        {
            "first_name": "Updated",
            "email": " UPDATED@Example.COM ",
            "mobile_number": "+91 98765 43212",
            "profile_image": "https://example.test/profile-placeholder.png",
        },
        format="json",
    )

    assert response.status_code == 200
    user.refresh_from_db()
    assert user.email == "updated@example.com"
    assert user.mobile_number == "+919876543212"
    assert AuthenticationAuditEvent.objects.filter(
        event=AuthenticationAuditEvent.Event.PROFILE_UPDATE, user=user
    ).exists()


@pytest.mark.django_db
def test_profile_cannot_remove_every_login_identifier(api_client, user):
    tokens = login(api_client).data
    authorize(api_client, tokens["access"])

    response = api_client.patch(
        reverse("auth-profile"), {"email": "", "mobile_number": None}, format="json"
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_disabled_user_existing_access_token_is_rejected(api_client, user):
    access = login(api_client).data["access"]
    user.is_enabled = False
    user.save(update_fields=("is_enabled",))

    response = authorize(api_client, access).get(reverse("auth-profile"))

    assert response.status_code == 401


@pytest.mark.django_db
def test_login_rate_limit_uses_scoped_throttle(api_client, user, monkeypatch):
    monkeypatch.setitem(ScopedRateThrottle.THROTTLE_RATES, "auth_login", "1/minute")

    assert login(api_client, password="wrong").status_code == 401
    assert login(api_client, password="wrong").status_code == 429


@pytest.mark.django_db
def test_audit_ignores_malformed_forwarded_ip(api_client, user):
    response = api_client.post(
        reverse("auth-login"),
        {"identifier": user.email, "password": "wrong"},
        format="json",
        HTTP_X_FORWARDED_FOR="not-an-ip",
    )

    assert response.status_code == 401
    assert AuthenticationAuditEvent.objects.latest("created_at").ip_address is None
