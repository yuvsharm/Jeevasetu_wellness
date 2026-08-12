import hashlib

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role, RoleAssignment
from apps.accounts.role_policy import actor_role_scope, assign_role
from apps.practitioners.models import (
    PractitionerApplication,
    PractitionerAuditEvent,
    PractitionerProfile,
)
from apps.staff.models import StaffProfile
from apps.tenancy.models import ClinicMembership, OrganizationMembership

SAFE_AUDIT_KEYS = {"reason", "status", "document_kind", "therapy_id", "enabled"}

SUBMISSION_REQUIREMENTS = {
    "personal_details": {
        "full_legal_name": "Full legal name",
        "date_of_birth": "Date of birth",
        "mobile_number": "Mobile number",
        "email": "Email address",
        "current_address": "Current address",
    },
    "professional_details": {
        "college_institute": "College / institute",
        "awarding_body": "University / awarding body",
        "passing_year": "Passing year",
        "bio": "Professional bio",
    },
    "service_availability": {
        "city": "Service city",
        "state": "State",
        "pin_code": "Service area PIN code",
    },
}


def record_event(application, *, actor, action, metadata=None):
    safe = {key: value for key, value in (metadata or {}).items() if key in SAFE_AUDIT_KEYS}
    return PractitionerAuditEvent.objects.create(
        application=application,
        organization=application.organization,
        actor=actor,
        action=action,
        metadata=safe,
    )


def manager_can_access(actor, application):
    level, clinic_ids = actor_role_scope(actor, application.organization)
    if level == Role.OWNER:
        return True
    return level == Role.MANAGER and (
        clinic_ids is None
        or (application.clinic_id is not None and application.clinic_id in clinic_ids)
    )


def require_manager_scope(actor, application):
    if not manager_can_access(actor, application):
        raise PermissionDenied("Practitioner application is unavailable in this scope.")


def submission_missing_requirements(application):
    missing = []
    for section, fields in SUBMISSION_REQUIREMENTS.items():
        for field, label in fields.items():
            if not getattr(application, field):
                missing.append({"section": section, "code": field, "label": label})
    if not application.profile_photo:
        missing.append(
            {"section": "personal_details", "code": "profile_photo", "label": "Profile photo"}
        )
    uploaded = set(application.documents.values_list("kind", flat=True))
    for kind, label in (
        ("GOVERNMENT_ID", "Government identity proof"),
        ("QUALIFICATION", "Highest qualification certificate"),
    ):
        if kind not in uploaded:
            missing.append({"section": "documents", "code": kind, "label": label})
    if application.registration_number and "REGISTRATION" not in uploaded:
        missing.append(
            {
                "section": "documents",
                "code": "REGISTRATION",
                "label": "Professional registration / licence certificate",
            }
        )
    return missing


@transaction.atomic
def submit_application(application, *, actor):
    application = PractitionerApplication.objects.select_for_update().get(pk=application.pk)
    if application.applicant_id != actor.id:
        raise PermissionDenied("Only the applicant can submit this application.")
    if application.status in (
        PractitionerApplication.Status.SUBMITTED,
        PractitionerApplication.Status.RESUBMITTED,
    ):
        return application
    if application.status not in (
        PractitionerApplication.Status.DRAFT,
        PractitionerApplication.Status.CORRECTION_REQUIRED,
    ):
        raise ValidationError("This application cannot be submitted.")
    missing = submission_missing_requirements(application)
    if missing:
        raise ValidationError(
            {
                "detail": "Please complete the following before submitting.",
                "missing_requirements": missing,
            }
        )
    try:
        application.full_clean()
    except DjangoValidationError as error:
        raise ValidationError(
            error.message_dict if hasattr(error, "message_dict") else error.messages
        ) from error
    previous = application.status
    application.status = (
        PractitionerApplication.Status.RESUBMITTED
        if previous == PractitionerApplication.Status.CORRECTION_REQUIRED
        else PractitionerApplication.Status.SUBMITTED
    )
    application.submitted_at = timezone.now()
    application.correction_reason = ""
    application.save(update_fields=("status", "submitted_at", "correction_reason", "updated_at"))
    record_event(
        application,
        actor=actor,
        action=(
            PractitionerAuditEvent.Action.RESUBMITTED
            if previous == PractitionerApplication.Status.CORRECTION_REQUIRED
            else PractitionerAuditEvent.Action.SUBMITTED
        ),
    )
    return application


def review_application(application, *, actor, action, reason=""):
    require_manager_scope(actor, application)
    transitions = {
        "review": (
            (PractitionerApplication.Status.SUBMITTED, PractitionerApplication.Status.RESUBMITTED),
            PractitionerApplication.Status.UNDER_REVIEW,
            PractitionerAuditEvent.Action.REVIEW_STARTED,
        ),
        "correction": (
            (
                PractitionerApplication.Status.SUBMITTED,
                PractitionerApplication.Status.RESUBMITTED,
                PractitionerApplication.Status.UNDER_REVIEW,
            ),
            PractitionerApplication.Status.CORRECTION_REQUIRED,
            PractitionerAuditEvent.Action.CORRECTION_REQUESTED,
        ),
        "reject": (
            (
                PractitionerApplication.Status.SUBMITTED,
                PractitionerApplication.Status.RESUBMITTED,
                PractitionerApplication.Status.UNDER_REVIEW,
            ),
            PractitionerApplication.Status.REJECTED,
            PractitionerAuditEvent.Action.REJECTED,
        ),
    }
    if action not in transitions:
        raise ValidationError({"detail": "Unsupported review action."})
    allowed, target, event = transitions[action]
    if application.status not in allowed:
        raise ValidationError({"detail": "This review transition is not permitted."})
    if action in ("correction", "reject") and not reason.strip():
        raise ValidationError({"detail": "A reason is required."})
    application.status = target
    application.reviewed_by = actor
    application.reviewed_at = timezone.now()
    if action == "correction":
        application.correction_reason = reason.strip()[:500]
    if action == "reject":
        application.rejection_reason = reason.strip()[:500]
    application.save()
    record_event(application, actor=actor, action=event, metadata={"reason": reason.strip()[:255]})
    return application


@transaction.atomic
def approve_application(application, *, actor):
    locked = (
        PractitionerApplication.objects.select_for_update()
        .select_related("applicant", "organization")
        .get(pk=application.pk)
    )
    require_manager_scope(actor, locked)
    if locked.status == PractitionerApplication.Status.APPROVED:
        return locked
    if locked.status not in (
        PractitionerApplication.Status.SUBMITTED,
        PractitionerApplication.Status.RESUBMITTED,
        PractitionerApplication.Status.UNDER_REVIEW,
    ):
        raise ValidationError({"detail": "This application cannot be approved."})
    if not locked.competencies.filter(verification_status="VERIFIED").exists():
        raise ValidationError({"detail": "At least one verified competency is required."})
    if locked.documents.filter(verification_status="VERIFIED").count() < 2:
        raise ValidationError({"detail": "Required documents must be verified."})

    staff_profile = None
    if locked.category == PractitionerApplication.Category.PHYSIOTHERAPIST:
        if locked.clinic is None:
            raise ValidationError({"detail": "A clinic is required for Physiotherapist activation."})
        membership, _ = OrganizationMembership.objects.get_or_create(
            user=locked.applicant, organization=locked.organization
        )
        if not membership.is_active:
            raise ValidationError({"detail": "The applicant organization membership is inactive."})
        ClinicMembership.objects.get_or_create(
            organization_membership=membership, clinic=locked.clinic
        )
        staff_profile, _ = StaffProfile.objects.get_or_create(
            user=locked.applicant,
            organization=locked.organization,
            defaults={
                "clinic": locked.clinic,
                "staff_type": Role.PHYSIOTHERAPIST,
                "gender": locked.gender,
                "date_of_birth": locked.date_of_birth,
                "qualification": locked.get_highest_qualification_display(),
                "registration_number": locked.registration_number,
                "experience_years": locked.experience_years,
                "languages_known": locked.languages,
                "alternate_mobile": (
                    locked.alternate_mobile[-10:] if locked.alternate_mobile else ""
                ),
                "emergency_contact": locked.mobile_number[-10:],
                "current_address": locked.current_address,
                "city": locked.city,
                "pin_code": locked.pin_code,
                "joining_date": timezone.localdate(),
                "bio": locked.bio,
            },
        )
        if staff_profile.staff_type != Role.PHYSIOTHERAPIST:
            raise ValidationError({"detail": "An incompatible staff profile already exists."})
        if not RoleAssignment.objects.filter(
            user=locked.applicant,
            organization=locked.organization,
            clinic=locked.clinic,
            role=Role.PHYSIOTHERAPIST,
            is_active=True,
        ).exists():
            assign_role(
                actor=actor,
                target=locked.applicant,
                organization=locked.organization,
                clinic=locked.clinic,
                role=Role.PHYSIOTHERAPIST,
            )

    profile, _ = PractitionerProfile.objects.update_or_create(
        user=locked.applicant,
        organization=locked.organization,
        defaults={
            "clinic": locked.clinic,
            "staff_profile": staff_profile,
            "category": locked.category,
            "qualification_specialization": locked.specialization,
            "is_approved": True,
            "is_publicly_visible": True,
            "approved_at": timezone.now(),
        },
    )
    locked.status = PractitionerApplication.Status.APPROVED
    locked.reviewed_by = actor
    locked.reviewed_at = timezone.now()
    locked.approved_profile = profile
    locked.save(
        update_fields=("status", "reviewed_by", "reviewed_at", "approved_profile", "updated_at")
    )
    record_event(locked, actor=actor, action=PractitionerAuditEvent.Action.APPROVED)
    return locked


def set_open_to_work(profile, *, actor, enabled):
    if profile.user_id != actor.id or not profile.is_approved:
        raise PermissionDenied("Open to Work is unavailable.")
    if enabled and profile.staff_profile_id is None:
        raise ValidationError("This category has no operational role yet.")
    profile.is_open_to_work = enabled
    profile.save(update_fields=("is_open_to_work", "updated_at"))
    record_event(
        profile.source_application,
        actor=actor,
        action=PractitionerAuditEvent.Action.OPEN_TO_WORK_CHANGED,
        metadata={"enabled": enabled},
    )
    return profile


def upload_checksum(file):
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()
