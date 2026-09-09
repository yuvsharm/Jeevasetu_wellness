from datetime import date
from unittest.mock import patch

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.practitioners.models import PractitionerApplication, PractitionerAuditEvent, PractitionerProfile
from apps.staff.models import StaffProfile
from tests.test_practitioner_dob import create_public
from tests.test_staff import headers

pytestmark = pytest.mark.django_db


def therapist(api_client):
    org, clinic, staff, profile = create_public(api_client)
    staff.user.set_password("Existing-Password-2026!")
    staff.user.save(update_fields=["password"])
    api_client.force_authenticate(staff.user)
    return org, clinic, staff, profile


def test_dob_partial_save_ignores_unrelated_legacy_blanks_and_persists(api_client):
    org, _, staff, profile = therapist(api_client)
    StaffProfile.objects.filter(pk=staff.pk).update(date_of_birth=None, current_address="", city="", pin_code="")
    response = api_client.patch(reverse("staff-me"), {"date_of_birth": "1995-08-15"}, format="json", **headers(org))
    assert response.status_code == 200, response.data
    staff.refresh_from_db()
    assert staff.date_of_birth == date(1995, 8, 15)
    assert (staff.current_address, staff.city, staff.pin_code) == ("", "", "")
    fresh = api_client.get(reverse("staff-me"), **headers(org))
    assert fresh.data["date_of_birth"] == "1995-08-15"
    from apps.practitioners.serializers import PublicPractitionerSerializer
    profile.refresh_from_db()
    assert PublicPractitionerSerializer(profile).data["age"] == fresh.data["age"]


@pytest.mark.parametrize("payload", [
    {"date_of_birth": "1995-02-30"}, {"date_of_birth": "2099-01-01"},
    {"date_of_birth": "2020-01-01"}, {"date_of_birth": "1900-01-01"},
    {"date_of_birth": "1995-08-15", "pin_code": "invalid"},
])
def test_invalid_submitted_fields_still_fail_without_partial_save(api_client, payload):
    org, _, staff, _ = therapist(api_client)
    original = staff.date_of_birth
    response = api_client.patch(reverse("staff-me"), payload, format="json", **headers(org))
    assert response.status_code == 400, response.data
    staff.refresh_from_db()
    assert staff.date_of_birth == original


def test_owner_created_open_to_work_persists_and_audits_without_application(api_client):
    org, _, staff, profile = therapist(api_client)
    counts = (User.objects.count(), StaffProfile.objects.count(), PractitionerProfile.objects.count(), PractitionerApplication.objects.count())
    url = "/api/v1/practitioners/me/open-to-work/"
    for enabled in (False, True):
        response = api_client.post(url, {"enabled": enabled}, format="json", **headers(org))
        assert response.status_code == 200, response.data
        profile.refresh_from_db()
        assert profile.is_open_to_work is enabled
        assert api_client.get(url, **headers(org)).data == {"is_open_to_work": enabled}
    events = PractitionerAuditEvent.objects.filter(profile=profile).order_by("created_at")
    assert [event.metadata for event in events] == [{"enabled": False}, {"enabled": True}]
    assert all(event.application_id is None and event.actor_id == staff.user_id for event in events)
    assert counts == (User.objects.count(), StaffProfile.objects.count(), PractitionerProfile.objects.count(), PractitionerApplication.objects.count())


def test_open_to_work_audit_failure_rolls_back_state(api_client):
    org, _, _, profile = therapist(api_client)
    original = profile.is_open_to_work
    from apps.practitioners.services import set_open_to_work
    with patch("apps.practitioners.services.PractitionerAuditEvent.objects.create", side_effect=RuntimeError("audit unavailable")):
        with pytest.raises(RuntimeError):
            set_open_to_work(profile, actor=profile.user, enabled=not original)
    profile.refresh_from_db()
    assert profile.is_open_to_work is original


@pytest.mark.parametrize("state", ["unapproved", "inactive_role", "inactive_membership", "unactivated"])
def test_open_to_work_does_not_bypass_eligibility(api_client, state):
    org, _, staff, profile = therapist(api_client)
    if state == "unapproved":
        profile.is_approved = False
        profile.save()
    elif state == "inactive_role":
        staff.user.role_assignments.update(is_active=False)
    elif state == "inactive_membership":
        staff.user.organization_memberships.update(is_active=False)
    else:
        staff.user.set_unusable_password()
        staff.user.save()
    response = api_client.post("/api/v1/practitioners/me/open-to-work/", {"enabled": False}, format="json", **headers(org))
    assert response.status_code == 403
    assert not PractitionerAuditEvent.objects.filter(profile=profile).exists()
