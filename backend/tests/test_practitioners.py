from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import Role, RoleAssignment, User
from apps.appointments.models import AppointmentRequest, TherapyOption
from apps.practitioners.models import (
    PractitionerApplication,
    PractitionerAuditEvent,
    PractitionerCompetency,
    PractitionerDocument,
)
from apps.practitioners.services import approve_application, set_open_to_work
from apps.tenancy.models import Clinic, ClinicMembership, Organization, OrganizationMembership

pytestmark = pytest.mark.django_db


def identity(organization, username, role=Role.CUSTOMER, clinic=None):
    user = User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        mobile_number=f"+919{abs(hash(username)) % 1000000000:09d}",
    )
    membership = OrganizationMembership.objects.create(user=user, organization=organization)
    clinic_membership = (
        ClinicMembership.objects.create(organization_membership=membership, clinic=clinic)
        if clinic
        else None
    )
    RoleAssignment.objects.create(
        user=user,
        organization=organization,
        organization_membership=membership,
        clinic=clinic,
        clinic_membership=clinic_membership,
        role=role,
    )
    return user


@pytest.fixture
def domain():
    organization = Organization.objects.create(
        legal_name="JeevaSetu", display_name="JeevaSetu", slug="practitioner-test"
    )
    clinic = Clinic.objects.create(organization=organization, name="Meerut", slug="meerut")
    therapy = TherapyOption.objects.create(
        organization=organization, name="Physiotherapy", slug="physiotherapy"
    )
    applicant = identity(organization, "applicant")
    manager = identity(organization, "manager", Role.MANAGER, clinic)
    owner = identity(organization, "owner", Role.OWNER)
    return organization, clinic, therapy, applicant, manager, owner


def application(domain, status=PractitionerApplication.Status.DRAFT):
    organization, clinic, therapy, applicant, _, _ = domain
    value = PractitionerApplication.objects.create(
        applicant=applicant,
        organization=organization,
        clinic=clinic,
        status=status,
        category="PHYSIOTHERAPIST",
        full_legal_name="Dr Asha Sharma",
        date_of_birth=date(1990, 1, 1),
        gender="FEMALE",
        mobile_number="9876543210",
        email="asha@example.com",
        current_address="Shastri Nagar",
        city="Meerut",
        state="Uttar Pradesh",
        pin_code="250004",
        highest_qualification="MPT",
        specialization="Orthopaedic",
        college_institute="Institute",
        awarding_body="University",
        passing_year=2014,
        experience_years=9,
        experience_months=2,
        bio="Experienced home-service practitioner.",
        languages=["Hindi", "English"],
    )
    PractitionerCompetency.objects.create(application=value, therapy=therapy, experience_months=60)
    for kind in ("GOVERNMENT_ID", "QUALIFICATION"):
        PractitionerDocument.objects.create(
            application=value,
            kind=kind,
            file=SimpleUploadedFile(f"{kind}.pdf", b"%PDF-1.4 safe"),
            original_name=f"{kind}.pdf",
            content_type="application/pdf",
            size_bytes=13,
            checksum_sha256="a" * 64,
        )
    return value


def headers(organization):
    return {"HTTP_X_ORGANIZATION_SLUG": organization.slug}


def test_applicant_isolation_and_cross_tenant_denial(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    outsider = User.objects.create_user(username="outsider")
    api_client.force_authenticate(outsider)
    assert (
        api_client.get(
            reverse("practitioner-my-application", args=[value.id]), **headers(organization)
        ).status_code
        == 403
    )
    api_client.force_authenticate(applicant)
    assert (
        api_client.get(
            reverse("practitioner-my-application", args=[value.id]), **headers(organization)
        ).status_code
        == 200
    )


def test_private_document_denies_customer_and_other_applicant(api_client, domain):
    organization, _, _, _, _, _ = domain
    value = application(domain)
    other = identity(organization, "other")
    api_client.force_authenticate(other)
    response = api_client.get(
        reverse("practitioner-document", args=[value.documents.first().id]), **headers(organization)
    )
    assert response.status_code == 403


def test_correction_and_rejection_workflow_is_audited(api_client, domain):
    organization, _, _, _, manager, _ = domain
    value = application(domain, "SUBMITTED")
    api_client.force_authenticate(manager)
    corrected = api_client.post(
        reverse("practitioner-review", args=[value.id]),
        {"action": "correction", "reason": "Replace blurred certificate."},
        format="json",
        **headers(organization),
    )
    assert corrected.status_code == 200 and corrected.data["status"] == "CORRECTION_REQUIRED"
    value.status = "SUBMITTED"
    value.save(update_fields=("status",))
    rejected = api_client.post(
        reverse("practitioner-review", args=[value.id]),
        {"action": "reject", "reason": "Qualification could not be verified."},
        format="json",
        **headers(organization),
    )
    assert rejected.status_code == 200 and rejected.data["status"] == "REJECTED"
    assert PractitionerAuditEvent.objects.filter(application=value).count() == 2


def test_applicant_cannot_self_approve_or_self_promote(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain, "SUBMITTED")
    api_client.force_authenticate(applicant)
    assert (
        api_client.post(
            reverse("practitioner-review", args=[value.id]),
            {"action": "approve"},
            format="json",
            **headers(organization),
        ).status_code
        == 403
    )
    assert not RoleAssignment.objects.filter(user=applicant, role=Role.PHYSIOTHERAPIST).exists()


def test_approval_is_idempotent_and_activates_existing_architecture(domain):
    organization, clinic, _, applicant, manager, _ = domain
    value = application(domain, "UNDER_REVIEW")
    value.competencies.update(verification_status="VERIFIED", verified_by=manager)
    value.documents.update(verification_status="VERIFIED", verified_by=manager)
    first = approve_application(value, actor=manager)
    second = approve_application(first, actor=manager)
    assert first.approved_profile_id == second.approved_profile_id
    assert (
        RoleAssignment.objects.filter(
            user=applicant,
            organization=organization,
            clinic=clinic,
            role=Role.PHYSIOTHERAPIST,
            is_active=True,
        ).count()
        == 1
    )


def test_open_to_work_requires_approved_operational_profile(domain):
    _, _, _, applicant, manager, _ = domain
    value = application(domain, "UNDER_REVIEW")
    value.competencies.update(verification_status="VERIFIED", verified_by=manager)
    value.documents.update(verification_status="VERIFIED", verified_by=manager)
    approved = approve_application(value, actor=manager)
    set_open_to_work(approved.approved_profile, actor=applicant, enabled=True)
    approved.approved_profile.refresh_from_db()
    assert approved.approved_profile.is_open_to_work


def test_public_profile_has_no_private_fields(api_client, domain):
    organization, _, _, _, manager, _ = domain
    value = application(domain, "UNDER_REVIEW")
    value.competencies.update(verification_status="VERIFIED", verified_by=manager)
    value.documents.update(verification_status="VERIFIED", verified_by=manager)
    value = approve_application(value, actor=manager)
    value.approved_profile.is_publicly_visible = True
    value.approved_profile.save()
    response = api_client.get(reverse("practitioner-public-list"), **headers(organization))
    payload = response.data[0]
    assert response.status_code == 200
    assert not (
        {"mobile_number", "email", "current_address", "documents", "registration_number"}
        & set(payload)
    )


def test_preferred_practitioner_never_assigns_request(domain):
    organization, _, therapy, applicant, manager, _ = domain
    value = application(domain, "UNDER_REVIEW")
    value.competencies.update(verification_status="VERIFIED", verified_by=manager)
    value.documents.update(verification_status="VERIFIED", verified_by=manager)
    value = approve_application(value, actor=manager)
    value.approved_profile.is_publicly_visible = True
    value.approved_profile.save()
    request = AppointmentRequest(
        preferred_practitioner=value.approved_profile,
        organization=organization,
        creator=applicant,
        therapy=therapy,
    )
    assert not hasattr(request, "physiotherapist")
