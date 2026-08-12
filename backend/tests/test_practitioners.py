import base64
from datetime import date
from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

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
    if role is not None:
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
    applicant = identity(organization, "applicant", role=None)
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
        profile_photo=SimpleUploadedFile("profile.jpg", b"\xff\xd8\xff test"),
    )
    PractitionerCompetency.objects.create(application=value, therapy=therapy, experience_months=60)
    for kind in ("GOVERNMENT_ID", "QUALIFICATION", "EXPERIENCE", "REGISTRATION"):
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


def test_roleless_applicant_creates_and_resumes_minimal_server_draft(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    api_client.force_authenticate(applicant)

    created = api_client.post(
        reverse("practitioner-my-applications"), {}, format="json", **headers(organization)
    )
    saved = api_client.patch(
        reverse("practitioner-my-application", args=[created.data["id"]]),
        {"full_legal_name": "Dr Saved Draft", "last_completed_step": 2},
        format="json",
        **headers(organization),
    )
    resumed = api_client.get(reverse("practitioner-my-applications"), **headers(organization))

    assert created.status_code == 201 and created.data["status"] == "DRAFT"
    assert saved.status_code == 200
    assert resumed.data[0]["full_legal_name"] == "Dr Saved Draft"
    assert resumed.data[0]["last_completed_step"] == 2
    assert not RoleAssignment.objects.filter(user=applicant).exists()


def test_frontend_shaped_autosave_payload_can_be_repeated(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)
    detail_url = reverse("practitioner-my-application", args=[value.id])
    current = api_client.get(detail_url, **headers(organization))
    payload = dict(current.data)
    payload.update(
        {
            "last_completed_step": 3,
            "availability_notes": "Weekdays after 10 AM",
            "languages": ["Hindi", "English"],
        }
    )

    first = api_client.patch(detail_url, payload, format="json", **headers(organization))
    second = api_client.patch(detail_url, payload, format="json", **headers(organization))

    assert first.status_code == 200, first.data
    assert second.status_code == 200, second.data
    assert (
        PractitionerApplication.objects.filter(
            applicant=applicant, organization=organization
        ).count()
        == 1
    )
    value.refresh_from_db()
    assert value.last_completed_step == 3
    assert value.availability_notes == "Weekdays after 10 AM"


def test_minimal_draft_with_nullable_fields_round_trips_without_500(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    api_client.force_authenticate(applicant)
    created = api_client.post(
        reverse("practitioner-my-applications"), {}, format="json", **headers(organization)
    )
    detail_url = reverse("practitioner-my-application", args=[created.data["id"]])
    payload = dict(api_client.get(detail_url, **headers(organization)).data)
    payload.update({"full_legal_name": "Dr Nullable Draft", "last_completed_step": 4})

    response = api_client.patch(detail_url, payload, format="json", **headers(organization))

    assert response.status_code == 200, response.data
    assert response.data["date_of_birth"] is None
    assert response.data["passing_year"] is None


def test_invalid_optional_autosave_value_returns_4xx_without_erasing_draft(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    original_name = value.full_legal_name
    api_client.force_authenticate(applicant)

    response = api_client.patch(
        reverse("practitioner-my-application", args=[value.id]),
        {"languages": {"invalid": "shape"}},
        format="json",
        **headers(organization),
    )

    assert response.status_code == 400
    assert "languages" in response.data
    value.refresh_from_db()
    assert value.full_legal_name == original_name


@pytest.mark.parametrize("kind", ["GOVERNMENT_ID", "QUALIFICATION", "EXPERIENCE"])
def test_document_categories_accept_real_pdf_only(api_client, domain, kind):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)
    accepted = api_client.post(
        reverse("practitioner-documents", args=[value.id]),
        {
            "kind": kind,
            "file": SimpleUploadedFile(
                "evidence.pdf", b"%PDF-1.4 safe", content_type="application/pdf"
            ),
        },
        format="multipart",
        **headers(organization),
    )
    disguised = api_client.post(
        reverse("practitioner-documents", args=[value.id]),
        {
            "kind": kind,
            "file": SimpleUploadedFile(
                "malware.pdf", b"MZ executable", content_type="application/pdf"
            ),
        },
        format="multipart",
        **headers(organization),
    )

    assert accepted.status_code == 201
    assert disguised.status_code == 400


def test_oversized_document_is_rejected(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)
    response = api_client.post(
        reverse("practitioner-documents", args=[value.id]),
        {
            "kind": "GOVERNMENT_ID",
            "file": SimpleUploadedFile(
                "large.pdf", b"%PDF-" + b"x" * (8 * 1024 * 1024), content_type="application/pdf"
            ),
        },
        format="multipart",
        **headers(organization),
    )
    assert response.status_code == 400


def test_profile_photo_accepts_image_and_rejects_pdf(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
        "AAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
    )
    accepted = api_client.post(
        reverse("practitioner-profile-photo", args=[value.id]),
        {"profile_photo": SimpleUploadedFile("photo.png", png, content_type="image/png")},
        format="multipart",
        **headers(organization),
    )
    rejected = api_client.post(
        reverse("practitioner-profile-photo", args=[value.id]),
        {
            "profile_photo": SimpleUploadedFile(
                "not-a-photo.pdf", b"%PDF-1.4", content_type="application/pdf"
            )
        },
        format="multipart",
        **headers(organization),
    )
    assert accepted.status_code == 200
    assert rejected.status_code == 400


@pytest.mark.parametrize(
    ("image_format", "extension", "content_type"),
    [("JPEG", "jpg", "image/jpeg"), ("PNG", "png", "image/png"), ("WEBP", "webp", "image/webp")],
)
def test_profile_photo_runtime_formats_are_readable(
    api_client, domain, image_format, extension, content_type
):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)
    buffer = BytesIO()
    Image.new("RGB", (256, 256), color=(28, 120, 90)).save(buffer, format=image_format)
    image_bytes = buffer.getvalue()
    if image_format == "JPEG" and len(image_bytes) < 15 * 1024:
        image_bytes += b"\0" * (15 * 1024 - len(image_bytes))

    response = api_client.post(
        reverse("practitioner-profile-photo", args=[value.id]),
        {
            "profile_photo": SimpleUploadedFile(
                f"profile.{extension}", image_bytes, content_type=content_type
            )
        },
        format="multipart",
        **headers(organization),
    )

    assert response.status_code == 200

    preview = api_client.get(
        reverse("practitioner-profile-photo", args=[value.id]), **headers(organization)
    )
    assert preview.status_code == 200
    assert preview["Content-Type"] == content_type


def test_corrupt_jpeg_returns_4xx_and_image_dependency_is_importable(api_client, domain):
    import PIL

    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)
    response = api_client.post(
        reverse("practitioner-profile-photo", args=[value.id]),
        {
            "profile_photo": SimpleUploadedFile(
                "corrupt.jpg", b"not-a-readable-jpeg", content_type="image/jpeg"
            )
        },
        format="multipart",
        **headers(organization),
    )

    assert PIL.__version__
    assert response.status_code == 400


def test_missing_required_fields_and_documents_keep_draft(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    api_client.force_authenticate(applicant)
    created = api_client.post(
        reverse("practitioner-my-applications"), {}, format="json", **headers(organization)
    )
    response = api_client.post(
        reverse("practitioner-submit", args=[created.data["id"]]),
        {},
        format="json",
        **headers(organization),
    )
    assert response.status_code == 400
    assert PractitionerApplication.objects.get(pk=created.data["id"]).status == "DRAFT"


def test_applicant_without_operational_role_can_open_and_submit_own_application(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    api_client.force_authenticate(applicant)

    opened = api_client.get(
        reverse("practitioner-my-application", args=[value.id]), **headers(organization)
    )
    submitted = api_client.post(
        reverse("practitioner-submit", args=[value.id]), {}, format="json", **headers(organization)
    )

    assert opened.status_code == 200
    assert submitted.status_code == 200
    assert submitted.data["status"] == "SUBMITTED"
    assert not RoleAssignment.objects.filter(user=applicant).exists()


def test_applicant_cannot_access_another_application(api_client, domain):
    organization, clinic, _, applicant, _, _ = domain
    other = identity(organization, "second-applicant", role=None)
    value = application(domain)
    value.applicant = other
    value.clinic = clinic
    value.save(update_fields=("applicant", "clinic"))
    api_client.force_authenticate(applicant)

    response = api_client.get(
        reverse("practitioner-my-application", args=[value.id]), **headers(organization)
    )

    assert response.status_code == 404


def test_private_document_denies_customer_and_other_applicant(api_client, domain):
    organization, _, _, _, _, _ = domain
    value = application(domain)
    other = identity(organization, "other")
    api_client.force_authenticate(other)
    response = api_client.get(
        reverse("practitioner-document", args=[value.documents.first().id]), **headers(organization)
    )
    assert response.status_code == 403


def test_applicant_can_preview_own_pdf_inline(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    document = value.documents.first()
    api_client.force_authenticate(applicant)

    response = api_client.get(
        reverse("practitioner-document-delete", args=[value.id, document.id]),
        **headers(organization),
    )

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith("inline;")
    assert b"".join(response.streaming_content).startswith(b"%PDF-")


def test_private_document_preview_enforces_owner_tenant_and_reviewer_scope(api_client, domain):
    organization, _, _, applicant, manager, owner = domain
    value = application(domain)
    document = value.documents.first()
    other_applicant = identity(organization, "preview-other", role=None)
    outsider = User.objects.create_user(username="preview-outsider")
    other_organization = Organization.objects.create(
        legal_name="Other", display_name="Other", slug="preview-other-tenant"
    )
    cross_tenant_user = identity(other_organization, "preview-cross-tenant", role=None)

    api_client.force_authenticate(other_applicant)
    assert (
        api_client.get(
            reverse("practitioner-document", args=[document.id]), **headers(organization)
        ).status_code
        == 403
    )
    api_client.force_authenticate(outsider)
    assert (
        api_client.get(
            reverse("practitioner-document", args=[document.id]), **headers(organization)
        ).status_code
        == 403
    )
    api_client.force_authenticate(cross_tenant_user)
    assert (
        api_client.get(
            reverse("practitioner-document", args=[document.id]),
            **headers(other_organization),
        ).status_code
        == 404
    )
    api_client.force_authenticate(manager)
    assert (
        api_client.get(
            reverse("practitioner-document", args=[document.id]), **headers(organization)
        ).status_code
        == 200
    )
    api_client.force_authenticate(owner)
    assert (
        api_client.get(
            reverse("practitioner-document", args=[document.id]), **headers(organization)
        ).status_code
        == 200
    )
    api_client.force_authenticate(applicant)
    assert (
        api_client.get(
            reverse("practitioner-document", args=[document.id]), **headers(organization)
        ).status_code
        == 200
    )


def test_replaced_and_deleted_documents_have_no_stale_preview(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    original = value.documents.get(kind="GOVERNMENT_ID")
    api_client.force_authenticate(applicant)

    replaced = api_client.post(
        reverse("practitioner-documents", args=[value.id]),
        {
            "kind": "GOVERNMENT_ID",
            "file": SimpleUploadedFile(
                "replacement.pdf", b"%PDF-1.4 replacement", content_type="application/pdf"
            ),
        },
        format="multipart",
        **headers(organization),
    )
    replacement_id = replaced.data["id"]
    stale_after_replace = api_client.get(
        reverse("practitioner-document", args=[original.id]), **headers(organization)
    )
    deleted = api_client.delete(
        reverse("practitioner-document-delete", args=[value.id, replacement_id]),
        **headers(organization),
    )
    stale_after_delete = api_client.get(
        reverse("practitioner-document", args=[replacement_id]), **headers(organization)
    )

    assert replaced.status_code == 201
    assert stale_after_replace.status_code == 404
    assert deleted.status_code == 204
    assert stale_after_delete.status_code == 404


def test_applicant_deletes_own_document_by_private_document_id(api_client, domain):
    organization, _, _, applicant, _, _ = domain
    value = application(domain)
    document = value.documents.get(kind="GOVERNMENT_ID")
    api_client.force_authenticate(applicant)

    deleted = api_client.delete(
        reverse("practitioner-document", args=[document.id]), **headers(organization)
    )
    stale = api_client.get(
        reverse("practitioner-document", args=[document.id]), **headers(organization)
    )

    assert deleted.status_code == 204
    assert stale.status_code == 404
    assert not value.documents.filter(kind="GOVERNMENT_ID").exists()


def test_private_profile_photo_returns_image_and_reviewer_is_authorized(api_client, domain):
    organization, _, _, applicant, manager, _ = domain
    value = application(domain)
    url = reverse("practitioner-private-profile-photo", args=[value.id])

    api_client.force_authenticate(applicant)
    own = api_client.get(url, **headers(organization))
    api_client.force_authenticate(manager)
    reviewed = api_client.get(url, **headers(organization))

    assert own.status_code == 200
    assert own["Content-Type"] == "image/jpeg"
    assert reviewed.status_code == 200


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
    assert corrected.data["reviewed_by"] == manager.id
    assert corrected.data["reviewer_name"] == manager.get_full_name()
    assert corrected.data["reviewed_at"]
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
