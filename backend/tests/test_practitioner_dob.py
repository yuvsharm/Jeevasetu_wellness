from datetime import date, datetime, timedelta, UTC
from unittest.mock import patch

import pytest
from django.urls import reverse
from rest_framework.exceptions import ValidationError

from apps.practitioners.dob import age_on, validate_dob
from apps.practitioners.models import PractitionerApplication, PractitionerProfile
from apps.staff.models import StaffProfile
from apps.availability.models import AvailabilityException
from tests.test_staff import actor, staff_payload, headers
from tests.test_practitioners import domain, application
from apps.practitioners.services import approve_application

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("today,expected", [(date(2026,12,19),35),(date(2026,12,20),36),(date(2026,12,21),36)])
def test_exact_birthday_age(today, expected):
    assert age_on(date(1990,12,20), today) == expected
    assert age_on(None, today) is None


@pytest.mark.parametrize("dob,message", [(None,"required"),(date(2027,1,1),"future"),(date(2011,1,1),"at least 18"),(date(1931,1,1),"no older than 80")])
def test_dob_bounds(dob, message):
    with pytest.raises(ValidationError, match=message):
        validate_dob(dob, date(2026,9,5))


def test_age_boundaries_and_leap_day():
    today = date(2026,9,5)
    assert validate_dob(date(2008,9,5), today) == date(2008,9,5)
    assert validate_dob(date(1945,9,6), today) == date(1945,9,6)
    with pytest.raises(ValidationError):
        validate_dob(date(2008,9,6), today)
    with pytest.raises(ValidationError):
        validate_dob(date(1945,9,5), today)
    assert age_on(date(2000,2,29),date(2025,2,28)) == 24
    assert age_on(date(2000,2,29),date(2025,3,1)) == 25


def test_new_therapist_requires_dob_manager_does_not(api_client):
    organization, clinic, owner = actor("OWNER")
    api_client.force_authenticate(owner)
    payload = staff_payload(clinic)
    payload.pop("date_of_birth")
    rejected = api_client.post(reverse("staff-list"), payload, format="json", **headers(organization))
    assert rejected.status_code == 400 and "date_of_birth" in rejected.data
    payload = staff_payload(None, "MANAGER", "2")
    payload.pop("date_of_birth")
    assert api_client.post(reverse("staff-list"),payload,format="json",**headers(organization)).status_code == 201


@pytest.mark.parametrize("dob", ["2027-01-01","2011-01-01","1931-01-01","2026-02-30"])
def test_owner_and_application_reject_same_invalid_dob(api_client, domain, dob):
    organization, clinic, _, applicant, _, owner = domain
    api_client.force_authenticate(owner)
    with patch("apps.practitioners.dob.timezone.now",return_value=datetime(2026,9,5,tzinfo=UTC)):
        owner_response = api_client.post(reverse("staff-list"),{**staff_payload(clinic),"date_of_birth":dob},format="json",**headers(organization))
        value = application(domain)
        api_client.force_authenticate(applicant)
        self_response = api_client.patch(reverse("practitioner-my-application",args=[value.pk]),{"date_of_birth":dob},format="json",**headers(organization))
    assert owner_response.status_code == self_response.status_code == 400
    assert "date_of_birth" in owner_response.data and "date_of_birth" in self_response.data


def test_approval_then_owner_edit_uses_staff_dob_everywhere(api_client, domain):
    organization, _, _, _, manager, owner = domain
    value = application(domain,"UNDER_REVIEW")
    value.competencies.update(verification_status="VERIFIED")
    value.documents.update(verification_status="VERIFIED")
    approved = approve_application(value, actor=manager)
    practitioner = approved.approved_profile
    staff = practitioner.staff_profile
    assert staff.date_of_birth == value.date_of_birth
    api_client.force_authenticate(owner)
    changed = api_client.patch(reverse("staff-detail",args=[staff.pk]),{"date_of_birth":"1991-12-20"},format="json",**headers(organization))
    assert changed.status_code == 200
    from apps.practitioners.serializers import ApplicationSerializer, PublicPractitionerSerializer
    approved.refresh_from_db()
    practitioner.refresh_from_db()
    with patch("apps.practitioners.dob.timezone.now",return_value=datetime(2026,9,5,tzinfo=UTC)):
        internal = ApplicationSerializer(approved).data
        public = PublicPractitionerSerializer(practitioner).data
    assert internal["date_of_birth"] == "1991-12-20" and internal["age"] == public["age"] == 34
    assert "date_of_birth" not in public
    # Enrollment snapshot remains historical; authorized responses follow staff.
    assert approved.date_of_birth == date(1990,1,1)


def create_public(api_client):
    organization, clinic, owner = actor("OWNER")
    api_client.force_authenticate(owner)
    created = api_client.post(reverse("staff-list"),staff_payload(clinic),format="json",**headers(organization))
    assert created.status_code == 201, created.data
    staff = StaffProfile.objects.get(pk=created.data["id"])
    practitioner = staff.practitioner_profile
    practitioner.is_publicly_visible = True
    practitioner.save()
    api_client.force_authenticate(None)
    return organization, clinic, staff, practitioner


def test_public_age_allowlist_and_legacy_dob(api_client):
    organization, _, staff, _ = create_public(api_client)
    url = reverse("practitioner-public-list")
    with patch("apps.practitioners.dob.timezone.now",return_value=datetime(2026,9,5,tzinfo=UTC)):
        public = api_client.get(url,**headers(organization)).data[0]
    assert public["age"] == 36
    assert not set(public) & {"date_of_birth","email","mobile","mobile_number","documents","current_address","password","internal_review_notes"}
    staff.date_of_birth = None
    staff.save(update_fields=["date_of_birth"])
    legacy = api_client.get(url,**headers(organization)).data[0]
    assert legacy["age"] is None
    assert StaffProfile.objects.filter(pk=staff.pk).exists()


@pytest.mark.parametrize("condition",["pending","rejected","inactive_role","disabled_user","inactive_user","hidden","unapproved","closed_clinic","inactive_membership","not_open_to_work"])
def test_public_eligibility_excludes_invalid_profiles(api_client, condition):
    organization, clinic, staff, practitioner = create_public(api_client)
    if condition in ("pending","rejected"):
        PractitionerApplication.objects.create(applicant=staff.user,organization=organization,clinic=clinic,approved_profile=practitioner,status="SUBMITTED" if condition=="pending" else "REJECTED")
    elif condition=="inactive_role": staff.user.role_assignments.update(is_active=False)
    elif condition=="inactive_membership":
        membership = staff.user.role_assignments.first().organization_membership
        membership.is_active=False; membership.save()
    elif condition in ("disabled_user","inactive_user"):
        setattr(staff.user,"is_enabled" if condition=="disabled_user" else "is_active",False);staff.user.save()
    elif condition=="closed_clinic": clinic.is_active=False;clinic.save()
    else:
        setattr(practitioner,{"hidden":"is_publicly_visible","unapproved":"is_approved","not_open_to_work":"is_open_to_work"}[condition],False);practitioner.save()
    assert api_client.get(reverse("practitioner-public-list"),**headers(organization)).data == []


@pytest.mark.parametrize("day,visible",[(16,False),(17,True),(14,True)])
def test_leave_uses_current_clinic_date_not_utc_date(api_client, day, visible):
    organization, clinic, staff, _ = create_public(api_client)
    from zoneinfo import ZoneInfo
    zone=ZoneInfo("Asia/Kolkata")
    start=datetime(2026,9,day,tzinfo=zone)
    AvailabilityException.objects.create(organization=organization,clinic=clinic,physiotherapist=staff,
        kind="UNAVAILABLE",starts_at=start,ends_at=start+timedelta(days=1),reason="Leave",
        approval_status="APPROVED",is_active=True,submitted_by=staff.user)
    # UTC is September 15; the clinic's current date is September 16.
    with patch("apps.practitioners.views.timezone.now",return_value=datetime(2026,9,15,20,tzinfo=UTC)):
        result=api_client.get(reverse("practitioner-public-list"),**headers(organization))
    assert bool(result.data) == visible


def test_dob_preview_is_stateless_and_returns_only_age(api_client):
    organization, _, _ = actor("OWNER")
    before=StaffProfile.objects.count()
    response=api_client.post(reverse("practitioner-dob-preview"),{"date_of_birth":"1990-01-01"},format="json",**headers(organization))
    assert response.status_code == 200 and set(response.data)=={"age"}
    assert response["Cache-Control"] == "private, no-store"
    assert StaffProfile.objects.count()==before
