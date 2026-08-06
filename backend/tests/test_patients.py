from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role, RoleAssignment, User
from apps.patients.models import PatientAddress, PatientProfile, PatientStatusAudit
from apps.tenancy.models import Clinic, ClinicMembership, Organization, OrganizationMembership

pytestmark = pytest.mark.django_db


def actor(role, *, slug, clinic_scoped=False):
    organization = Organization.objects.create(legal_name=slug, display_name=slug, slug=slug)
    clinic = Clinic.objects.create(organization=organization, name="Meerut", slug="meerut")
    user = User.objects.create_user(
        username=f"{role.lower()}-{slug}",
        email=f"{role.lower()}-{slug}@example.com",
        password="Safe-test-password-1",
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    clinic_membership = None
    if clinic_scoped:
        clinic_membership = ClinicMembership.objects.create(
            organization_membership=membership, clinic=clinic
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


def headers(organization):
    return {"HTTP_X_ORGANIZATION_SLUG": organization.slug}


def payload(clinic, *, mobile="9876543210", age=28):
    return {
        "full_name": "Asha Sharma",
        "mobile_number": mobile,
        "email": "asha@example.com",
        "gender": "FEMALE",
        "age": age,
        "clinic": str(clinic.id),
        "emergency_contact_name": "Yash Sharma",
        "emergency_contact_relationship": "Brother",
        "emergency_contact_mobile": "9876543299",
        "guardian_name": "",
        "guardian_relationship": "",
        "guardian_mobile": "",
        "addresses": [
            {
                "label": "Home",
                "address_line_1": "Shastri Nagar",
                "city": "Meerut",
                "region": "Uttar Pradesh",
                "pin_code": "250004",
                "is_primary": True,
            }
        ],
        "caregivers": [],
    }


def test_owner_creates_paginated_patient_with_immutable_identifier(api_client):
    organization, clinic, owner = actor(Role.OWNER, slug="patient-owner")
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("patient-list-create"), payload(clinic), format="json", **headers(organization)
    )
    assert created.status_code == 201
    assert created.data["patient_identifier"] == "PAT-000001"
    patient = PatientProfile.objects.get(pk=created.data["id"])
    assert patient.addresses.filter(is_primary=True, is_active=True).count() == 1
    changed = api_client.patch(
        reverse("patient-detail", args=[patient.pk]),
        {"patient_identifier": "PAT-999999", "full_name": "Asha S."},
        format="json",
        **headers(organization),
    )
    patient.refresh_from_db()
    assert changed.status_code == 200 and patient.patient_identifier == "PAT-000001"
    listed = api_client.get(reverse("patient-list-create"), **headers(organization))
    assert listed.data["count"] == 1
    assert listed.data["results"][0]["mobile_hint"] == "******3210"
    assert "mobile_number" not in listed.data["results"][0]


def test_duplicate_active_mobile_is_rejected_without_merging(api_client):
    organization, clinic, owner = actor(Role.OWNER, slug="patient-duplicate")
    api_client.force_authenticate(owner)
    first = api_client.post(
        reverse("patient-list-create"), payload(clinic), format="json", **headers(organization)
    )
    second = api_client.post(
        reverse("patient-list-create"),
        payload(clinic, mobile="+91 98765 43210"),
        format="json",
        **headers(organization),
    )
    assert first.status_code == 201 and second.status_code == 400
    assert PatientProfile.objects.filter(organization=organization).count() == 1


def test_minor_requires_complete_guardian_details(api_client):
    organization, clinic, owner = actor(Role.OWNER, slug="patient-minor")
    api_client.force_authenticate(owner)
    invalid = api_client.post(
        reverse("patient-list-create"),
        payload(clinic, age=12),
        format="json",
        **headers(organization),
    )
    valid_payload = payload(clinic, mobile="9876543211", age=12)
    valid_payload.update(
        guardian_name="Ravi Sharma",
        guardian_relationship="Father",
        guardian_mobile="9876543288",
    )
    valid = api_client.post(
        reverse("patient-list-create"), valid_payload, format="json", **headers(organization)
    )
    assert invalid.status_code == 400 and valid.status_code == 201


def test_address_limit_and_primary_address_are_enforced(api_client):
    organization, clinic, owner = actor(Role.OWNER, slug="patient-address")
    api_client.force_authenticate(owner)
    data = payload(clinic)
    data["addresses"] = [
        {
            "label": f"Address {index}",
            "address_line_1": "Meerut",
            "city": "Meerut",
            "region": "Uttar Pradesh",
            "pin_code": "250004",
            "is_primary": index == 0,
        }
        for index in range(5)
    ]
    response = api_client.post(
        reverse("patient-list-create"), data, format="json", **headers(organization)
    )
    assert response.status_code == 400


def test_manager_is_clinic_scoped_and_cannot_transfer_patient(api_client):
    organization, clinic, manager = actor(Role.MANAGER, slug="patient-manager", clinic_scoped=True)
    other_clinic = Clinic.objects.create(organization=organization, name="Delhi", slug="delhi")
    api_client.force_authenticate(manager)
    created = api_client.post(
        reverse("patient-list-create"), payload(clinic), format="json", **headers(organization)
    )
    transferred = api_client.patch(
        reverse("patient-detail", args=[created.data["id"]]),
        {"clinic": str(other_clinic.id)},
        format="json",
        **headers(organization),
    )
    hidden = api_client.post(
        reverse("patient-list-create"),
        payload(other_clinic, mobile="9876543211"),
        format="json",
        **headers(organization),
    )
    assert created.status_code == 201
    assert transferred.status_code == 400 and hidden.status_code == 400


def test_physiotherapist_has_no_directory_access(api_client):
    organization, _, physiotherapist = actor(
        Role.PHYSIOTHERAPIST, slug="patient-physio", clinic_scoped=True
    )
    api_client.force_authenticate(physiotherapist)
    response = api_client.get(reverse("patient-list-create"), **headers(organization))
    assert response.status_code == 403


def test_status_is_audited_and_no_delete_route_exists(api_client):
    organization, clinic, owner = actor(Role.OWNER, slug="patient-status")
    api_client.force_authenticate(owner)
    created = api_client.post(
        reverse("patient-list-create"), payload(clinic), format="json", **headers(organization)
    )
    response = api_client.post(
        reverse("patient-status", args=[created.data["id"]]),
        {"is_active": False, "reason": "Duplicate registration review"},
        format="json",
        **headers(organization),
    )
    deleted = api_client.delete(
        reverse("patient-detail", args=[created.data["id"]]), **headers(organization)
    )
    assert response.status_code == 200 and response.data["is_active"] is False
    assert PatientStatusAudit.objects.filter(patient_id=created.data["id"]).count() == 1
    assert deleted.status_code == 405


def test_photo_validation_and_authorized_delivery(api_client, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    organization, clinic, owner = actor(Role.OWNER, slug="patient-photo")
    patient = PatientProfile.objects.create(
        organization=organization,
        clinic=clinic,
        full_name="Asha Sharma",
        mobile_number="9876543210",
        gender="FEMALE",
        date_of_birth=date(1990, 1, 1),
        profile_photo=SimpleUploadedFile("asha.png", b"png-data", content_type="image/png"),
        emergency_contact_name="Yash Sharma",
        emergency_contact_relationship="Brother",
        emergency_contact_mobile="9876543299",
    )
    PatientAddress.objects.create(
        patient=patient,
        address_line_1="Meerut",
        city="Meerut",
        region="Uttar Pradesh",
        pin_code="250004",
        is_primary=True,
    )
    anonymous = api_client.get(reverse("patient-photo", args=[patient.pk]), **headers(organization))
    api_client.force_authenticate(owner)
    authorized = api_client.get(
        reverse("patient-photo", args=[patient.pk]), **headers(organization)
    )
    assert anonymous.status_code == 401 and authorized.status_code == 200
