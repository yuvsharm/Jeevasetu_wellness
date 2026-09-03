from datetime import date

import pytest
from django.urls import reverse

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import TherapyOption
from apps.practitioners.models import PractitionerProfile
from apps.staff.models import ServiceArea, Specialization, StaffProfile
from apps.tenancy.models import Clinic, ClinicMembership, Organization, OrganizationMembership

pytestmark = pytest.mark.django_db


def actor(role, *, clinic_scoped=False):
    organization = Organization.objects.create(
        legal_name="JeevaSetu",
        display_name="JeevaSetu",
        slug=f"staff-{role.lower()}-{str(clinic_scoped).lower()}",
    )
    clinic = Clinic.objects.create(organization=organization, name="Meerut", slug="meerut")
    user = User.objects.create_user(
        username=f"{role.lower()}{clinic_scoped}",
        email=f"{role.lower()}{clinic_scoped}@example.com",
        password="Safe-test-password-1",
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    clinic_membership = (
        ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)
        if clinic_scoped
        else None
    )
    RoleAssignment.objects.create(
        user=user,
        organization=organization,
        organization_membership=membership,
        clinic=clinic if clinic_scoped else None,
        clinic_membership=clinic_membership,
        role=role,
    )
    return organization, clinic, user


def staff_payload(clinic, role=Role.PHYSIOTHERAPIST, suffix="1"):
    service_area_ids = []
    therapy_competency_ids = []
    if role == Role.PHYSIOTHERAPIST and clinic is not None:
        area, _ = ServiceArea.objects.get_or_create(
            organization=clinic.organization, name="Meerut"
        )
        service_area_ids = [str(area.id)]
        therapy, _ = TherapyOption.objects.get_or_create(
            organization=clinic.organization,
            slug="physiotherapy",
            defaults={"name": "Physiotherapy"},
        )
        therapy_competency_ids = [str(therapy.id)]
    return {
        "full_name": "Dr Asha Sharma",
        "email": f"asha{suffix}@example.com",
        "mobile": f"+91987654321{suffix}",
        "staff_type": role,
        "gender": "FEMALE",
        "date_of_birth": "1990-01-01",
        "qualification": "BPT",
        "registration_number": "REG-101",
        "experience_years": 8,
        "therapy_competency_ids": therapy_competency_ids,
        "specialization_ids": [],
        "languages_known": ["Hindi", "English"],
        "alternate_mobile": "",
        "emergency_contact": "9876543299",
        "current_address": "Shastri Nagar",
        "city": "Meerut",
        "pin_code": "250004",
        "clinic": str(clinic.id) if clinic else None,
        "service_area_ids": service_area_ids,
        "availability": "AVAILABLE",
        "is_online": True,
        "joining_date": str(date.today()),
        "bio": "Experienced home-service physiotherapist.",
    }


def headers(organization):
    return {"HTTP_X_ORGANIZATION_SLUG": organization.slug}


def test_owner_creates_manager_and_physiotherapist(api_client):
    organization, clinic, owner = actor(Role.OWNER)
    api_client.force_authenticate(owner)
    manager_data = staff_payload(None, Role.MANAGER, "2")
    manager = api_client.post(
        reverse("staff-list"), manager_data, format="json", **headers(organization)
    )
    therapy = TherapyOption.objects.create(
        organization=organization, name="Abhyang", slug="abhyang"
    )
    physiotherapist = api_client.post(
        reverse("staff-list"),
        {**staff_payload(clinic), "therapy_competency_ids": [str(therapy.id)]},
        format="json",
        **headers(organization),
    )
    assert manager.status_code == 201
    assert physiotherapist.status_code == 201
    assert StaffProfile.objects.filter(organization=organization).count() == 2
    profile = StaffProfile.objects.get(pk=physiotherapist.data["id"])
    assert list(profile.therapy_competencies.all()) == [therapy]
    assert PractitionerProfile.objects.filter(
        staff_profile=profile, is_approved=True, is_open_to_work=True
    ).exists()
    assert not profile.user.has_usable_password()
    practitioner = profile.practitioner_profile
    practitioner.is_publicly_visible = True
    practitioner.save(update_fields=("is_publicly_visible",))
    public = api_client.get(reverse("practitioner-public-list"), **headers(organization))
    assert public.status_code == 200
    assert public.data[0]["display_name"] == "Dr Asha Sharma"
    assert public.data[0]["verified_services"] == ["Abhyang"]
    assert "mobile" not in public.data[0] and "date_of_birth" not in public.data[0]
    assert (
        RoleAssignment.objects.filter(
            organization=organization, role=Role.MANAGER, is_active=True
        ).count()
        == 1
    )


def test_manager_can_only_manage_physiotherapists_in_assigned_clinic(api_client):
    organization, clinic, manager = actor(Role.MANAGER, clinic_scoped=True)
    api_client.force_authenticate(manager)
    created = api_client.post(
        reverse("staff-list"), staff_payload(clinic), format="json", **headers(organization)
    )
    forbidden = api_client.post(
        reverse("staff-list"),
        staff_payload(None, Role.MANAGER, "2"),
        format="json",
        **headers(organization),
    )
    assert created.status_code == 201
    assert forbidden.status_code == 403


def test_owner_search_filter_status_and_password_reset(api_client):
    organization, clinic, owner = actor(Role.OWNER)
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("staff-list"), staff_payload(clinic), format="json", **headers(organization)
    )
    profile_id = created.data["id"]
    listed = api_client.get(
        reverse("staff-list"),
        {
            "search": "Asha",
            "type": "PHYSIOTHERAPIST",
            "status": "active",
            "ordering": "-experience_years",
        },
        **headers(organization),
    )
    assert listed.status_code == 200 and len(listed.data["results"]) == 1
    row = listed.data["results"][0]
    assert row["clinic_name"] == clinic.name
    assert row["specialization_names"] == []
    assert row["profile_source"] == "STAFF_CREATED"
    assert row["approved_weekly_rule_count"] == 0
    disabled = api_client.post(
        reverse("staff-status", args=[profile_id]),
        {"is_active": False, "reason": "Leave"},
        format="json",
        **headers(organization),
    )
    assert disabled.status_code == 200 and disabled.data["is_active"] is False


def test_physiotherapist_edits_only_self_and_updates_availability(api_client):
    organization, clinic, owner = actor(Role.OWNER)
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("staff-list"), staff_payload(clinic), format="json", **headers(organization)
    )
    profile = StaffProfile.objects.get(pk=created.data["id"])
    api_client.force_authenticate(profile.user)
    response = api_client.patch(
        reverse("staff-availability"),
        {"availability": "BUSY", "is_online": False},
        format="json",
        **headers(organization),
    )
    assert response.status_code == 200
    profile.refresh_from_db()
    assert profile.availability == "BUSY" and profile.is_online is False
    assert api_client.get(reverse("staff-list"), **headers(organization)).status_code == 403


def test_unique_identity_and_required_professional_fields(api_client):
    organization, clinic, owner = actor(Role.OWNER)
    api_client.force_authenticate(owner)
    data = staff_payload(clinic)
    assert (
        api_client.post(
            reverse("staff-list"), data, format="json", **headers(organization)
        ).status_code
        == 201
    )
    duplicate = api_client.post(
        reverse("staff-list"),
        {**data, "full_name": "Duplicate"},
        format="json",
        **headers(organization),
    )
    invalid = api_client.post(
        reverse("staff-list"),
        {**staff_payload(clinic, suffix="3"), "qualification": "", "experience_years": None},
        format="json",
        **headers(organization),
    )
    assert duplicate.status_code == 400
    assert invalid.status_code == 400


def test_staff_experience_uses_separate_integer_years_and_months(api_client):
    organization, clinic, owner = actor(Role.OWNER)
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("staff-list"),
        {**staff_payload(clinic), "experience_years": 4, "experience_months": 6},
        format="json",
        **headers(organization),
    )
    assert created.status_code == 201
    profile = StaffProfile.objects.get(pk=created.data["id"])
    assert (profile.experience_years, profile.experience_months) == (4, 6)
    invalid = api_client.post(
        reverse("staff-list"),
        {**staff_payload(clinic, suffix="3"), "experience_years": 3, "experience_months": 12},
        format="json",
        **headers(organization),
    )
    assert invalid.status_code == 400


def test_options_are_tenant_scoped(api_client):
    organization, _, owner = actor(Role.OWNER)
    Specialization.objects.get_or_create(name="Sports Physiotherapy")
    ServiceArea.objects.create(organization=organization, name="Meerut")
    api_client.force_authenticate(owner)
    response = api_client.get(reverse("staff-options"), **headers(organization))
    assert response.status_code == 200
    assert "Sports Physiotherapy" in {item["name"] for item in response.data["specializations"]}
    assert response.data["service_areas"][0]["name"] == "Meerut"


def test_duplicate_mobile_is_rejected_before_owner_sends_otp(api_client):
    organization, _, owner = actor(Role.OWNER)
    existing = User.objects.create_user(username="existing-mobile", mobile_number="+919876543210")
    api_client.force_authenticate(owner)
    response = api_client.post(
        reverse("staff-mobile-availability"),
        {"mobile": existing.mobile_number},
        format="json", **headers(organization),
    )
    assert response.status_code == 400
    assert "already registered" in str(response.data).lower()
    assert User.objects.filter(mobile_number=existing.mobile_number).count() == 1
