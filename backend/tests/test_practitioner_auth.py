from datetime import timedelta

import pytest
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.appointments.models import BookingPhoneVerification
from apps.practitioners.models import PractitionerApplication
from apps.staff.models import StaffProfile
from tests.test_customer_registration import issue, tenant, verify
from tests.test_staff import actor, headers, staff_payload

pytestmark = pytest.mark.django_db


def practitioner_payload(token, mobile="9876543210"):
    return {
        "booking_verification_token": token,
        "mobile_number": mobile,
        "full_name": "TEST Practitioner",
        "email": f"test-practitioner-{mobile}@example.com",
        "password": "Practitioner-Secure-2026!",
        "confirm_password": "Practitioner-Secure-2026!",
    }


@override_settings(MSG91_ENABLED=False)
def test_practitioner_registers_once_then_signs_in_and_creates_one_application(api_client):
    organization, _, _ = actor("OWNER")
    issued = issue(api_client, organization)
    verified = verify(api_client, organization, issued)
    created = api_client.post(
        reverse("auth-practitioner-register"), practitioner_payload(verified.data["token"]),
        format="json", **tenant(organization),
    )
    assert created.status_code == 201 and created.data["activated"] is False
    user = User.objects.get(mobile_number="+919876543210")
    assert user.check_password("Practitioner-Secure-2026!")

    BookingPhoneVerification.objects.filter(
        organization=organization, mobile_number="9876543210"
    ).update(created_at=timezone.now() - timedelta(days=1))
    cache.clear()
    second_issued = issue(api_client, organization)
    second_verified = verify(api_client, organization, second_issued)
    duplicate = api_client.post(
        reverse("auth-practitioner-register"), practitioner_payload(second_verified.data["token"]),
        format="json", **tenant(organization),
    )
    assert duplicate.status_code == 400
    assert "already registered" in str(duplicate.data).lower()
    assert User.objects.filter(mobile_number="+919876543210").count() == 1

    api_client.force_authenticate(user)
    first = api_client.post(reverse("practitioner-my-applications"), {}, format="json", **tenant(organization))
    second = api_client.get(reverse("practitioner-my-applications"), **tenant(organization))
    assert first.status_code == 201
    assert len(second.data) == 1
    assert PractitionerApplication.objects.filter(applicant=user, organization=organization).count() == 1


@override_settings(MSG91_ENABLED=False)
def test_owner_created_practitioner_activates_instead_of_registering_again(api_client):
    organization, clinic, owner = actor("OWNER")
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("staff-list"), staff_payload(clinic), format="json", **headers(organization)
    )
    assert created.status_code == 201
    profile = StaffProfile.objects.get(pk=created.data["id"])
    assert not profile.user.has_usable_password()

    api_client.force_authenticate(user=None)
    issued = issue(api_client, organization, mobile="9876543211")
    verified = verify(api_client, organization, issued, mobile="9876543211")
    activated = api_client.post(
        reverse("auth-practitioner-register"),
        practitioner_payload(verified.data["token"], mobile="9876543211"),
        format="json", **tenant(organization),
    )
    assert activated.status_code == 200 and activated.data["activated"] is True
    profile.user.refresh_from_db()
    assert profile.user.check_password("Practitioner-Secure-2026!")
    assert User.objects.filter(mobile_number="+919876543211").count() == 1
    assert StaffProfile.objects.filter(user=profile.user, organization=organization).count() == 1


@override_settings(MSG91_ENABLED=False)
def test_activation_endpoint_never_creates_identity_and_rejects_replay(api_client):
    organization, clinic, owner = actor("OWNER")
    before = User.objects.count()
    issued = issue(api_client, organization, mobile="9876543298")
    verified = verify(api_client, organization, issued, mobile="9876543298")
    missing = api_client.post(
        reverse("auth-practitioner-activate"),
        practitioner_payload(verified.data["token"], mobile="9876543298"),
        format="json", **tenant(organization),
    )
    assert missing.status_code == 400 and User.objects.count() == before

    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("staff-list"), staff_payload(clinic, suffix="7"), format="json", **headers(organization)
    )
    profile = StaffProfile.objects.get(pk=created.data["id"])
    original_ids = (profile.user_id, profile.id, profile.practitioner_profile.id)
    api_client.force_authenticate(user=None)
    issued = issue(api_client, organization, mobile="9876543217")
    verified = verify(api_client, organization, issued, mobile="9876543217")
    payload = practitioner_payload(verified.data["token"], mobile="9876543217")
    activated = api_client.post(
        reverse("auth-practitioner-activate"), payload, format="json", **tenant(organization)
    )
    replay = api_client.post(
        reverse("auth-practitioner-activate"), payload, format="json", **tenant(organization)
    )
    profile.refresh_from_db()
    assert activated.status_code == 200 and replay.status_code == 400
    assert original_ids == (profile.user_id, profile.id, profile.practitioner_profile.id)
    assert PractitionerApplication.objects.filter(applicant=profile.user).count() == 0


@override_settings(MSG91_ENABLED=False)
def test_owner_verified_manager_creation_hashes_staff_entered_password(api_client):
    organization, _, owner = actor("OWNER")
    issued = issue(api_client, organization, mobile="9876543212")
    verified = verify(api_client, organization, issued, mobile="9876543212")
    api_client.force_authenticate(owner)
    payload = {
        **staff_payload(None, role="MANAGER", suffix="2"),
        "mobile_verification_token": verified.data["token"],
        "password": "Manager-Secure-2026!",
        "confirm_password": "Manager-Secure-2026!",
    }
    created = api_client.post(
        reverse("staff-list"), payload, format="json", **headers(organization)
    )
    assert created.status_code == 201
    profile = StaffProfile.objects.get(pk=created.data["id"])
    assert profile.user.check_password("Manager-Secure-2026!")
    assert not profile.user.practitioner_profiles.exists()
