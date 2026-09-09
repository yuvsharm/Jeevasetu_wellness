import hashlib

from django.core.exceptions import PermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role, RoleAssignment
from apps.accounts.role_policy import actor_role_scope, assign_role
from apps.practitioners.models import (
    PractitionerApplication,
    PractitionerAuditEvent,
    PractitionerCompetency,
    PractitionerProfile,
)
from apps.staff.models import StaffProfile
from apps.practitioners.dob import validate_dob, identity_today
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
    requirements = SUBMISSION_REQUIREMENTS
    if application.qualification_title:
        requirements = {"personal_details": {"full_legal_name": "Full name", "date_of_birth": "Date of birth",
            "mobile_number": "Mobile", "email": "Email", "clinic": "Clinic", "languages": "Languages"},
            "professional_details": {"working_days": "Working days", "working_hours_start": "Working hours start",
                                     "working_hours_end": "Working hours end"}}
        if not application.service_areas.filter(is_active=True, organization=application.organization).exists():
            missing.append({"section": "service_availability", "code": "service_areas", "label": "Service areas"})
        if not application.competencies.exclude(
            verification_status=PractitionerCompetency.Verification.REJECTED
        ).filter(therapy__is_active=True, therapy__organization=application.organization).exists():
            missing.append({"section": "professional_details", "code": "competencies", "label": "Therapy competencies"})
    for section, fields in requirements.items():
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
    validate_dob(application.date_of_birth, identity_today(application))
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


@transaction.atomic
def review_application(application, *, actor, action, reason=""):
    application = PractitionerApplication.objects.select_for_update().get(pk=application.pk)
    require_manager_scope(actor, application)
    transitions = {
        "review": (
            (PractitionerApplication.Status.SUBMITTED, PractitionerApplication.Status.RESUBMITTED),
            PractitionerApplication.Status.UNDER_REVIEW,
            PractitionerAuditEvent.Action.REVIEW_STARTED,
        ),
        "correction": (
            (PractitionerApplication.Status.UNDER_REVIEW,),
            PractitionerApplication.Status.CORRECTION_REQUIRED,
            PractitionerAuditEvent.Action.CORRECTION_REQUESTED,
        ),
        "reject": (
            (PractitionerApplication.Status.UNDER_REVIEW,),
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
    if locked.status != PractitionerApplication.Status.UNDER_REVIEW:
        raise ValidationError({"detail": "Start review before approving this application."})
    validate_dob(locked.date_of_birth, identity_today(locked))
    current_competencies = locked.competencies.exclude(
        verification_status=PractitionerCompetency.Verification.REJECTED
    ).filter(therapy__is_active=True, therapy__organization=locked.organization)
    if not current_competencies.exists():
        raise ValidationError({"detail": "At least one therapy must be selected before approval."})
    verified_documents = set(
        locked.documents.filter(verification_status="VERIFIED").values_list("kind", flat=True)
    )
    if "GOVERNMENT_ID" not in verified_documents:
        raise ValidationError({"detail": "Government ID must be verified before approval."})
    if "QUALIFICATION" not in verified_documents:
        raise ValidationError({"detail": "Qualification document must be verified before approval."})
    if locked.qualification_title and submission_missing_requirements(locked):
        raise ValidationError({"detail": "Complete the required application information before approval."})

    staff_profile = None
    if locked.category == PractitionerApplication.Category.PHYSIOTHERAPIST or locked.qualification_title:
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
                "qualification": locked.qualification_title or locked.get_highest_qualification_display(),
                "registration_number": locked.registration_number,
                "experience_years": locked.experience_years,
                "experience_months": locked.experience_months,
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
        staff_profile.date_of_birth = locked.date_of_birth
        staff_profile.save(update_fields=["date_of_birth"])
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
    if staff_profile is not None:
        if locked.qualification_title:
            from apps.availability.models import AvailabilityRule
            staff_profile.service_areas.set(locked.service_areas.filter(is_active=True))
            for weekday in locked.working_days:
                AvailabilityRule.objects.get_or_create(organization=locked.organization, clinic=locked.clinic,
                    physiotherapist=staff_profile, weekday=weekday, effective_from=timezone.localdate(),
                    defaults={"starts_at": locked.working_hours_start, "ends_at": locked.working_hours_end,
                              "approval_status": "APPROVED", "is_active": True,
                              "submitted_by": locked.applicant, "reviewed_by": actor})
        staff_profile.therapy_competencies.add(
            *current_competencies.values_list("therapy_id", flat=True)
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


def competency_future_appointment(competency, profile):
    """Return one future assignment that would be invalidated by removing a therapy."""
    if profile is None or profile.staff_profile_id is None:
        return None
    from apps.appointments.models import Appointment

    return (
        Appointment.objects.filter(
            physiotherapist_id=profile.staff_profile_id,
            scheduled_start__gte=timezone.now(),
            status__in=Appointment.BLOCKING_STATUSES,
        )
        .filter(
            Q(therapy_id=competency.therapy_id)
            | Q(originating_request__requested_therapies__id=competency.therapy_id)
        )
        .order_by("scheduled_start")
        .first()
    )


@transaction.atomic
def add_competency(profile, therapy, *, actor):
    """Add an operational therapy while retaining the legacy competency audit record."""
    competency, _ = PractitionerCompetency.objects.select_for_update().get_or_create(
        profile=profile,
        therapy=therapy,
    )
    competency.verification_status = PractitionerCompetency.Verification.VERIFIED
    competency.verified_by = None
    competency.verified_at = None
    competency.save(update_fields=("verification_status", "verified_by", "verified_at"))
    profile.staff_profile.therapy_competencies.add(therapy)
    PractitionerAuditEvent.objects.create(
        profile=profile,
        organization=profile.organization,
        actor=actor,
        action="COMPETENCY_ADDED",
        metadata={"therapy_id": str(therapy.id), "therapy_name": therapy.name, "status": "SELECTED"},
    )
    return competency


@transaction.atomic
def remove_competency(competency, *, actor, profile=None):
    """Reject a claim and revoke operational eligibility without deleting its audit trail."""
    competency = PractitionerCompetency.objects.select_for_update(of=("self",)).select_related(
        "therapy", "application", "profile"
    ).get(pk=competency.pk)
    profile = profile or competency.profile or getattr(competency.application, "approved_profile", None)
    if competency.verification_status == PractitionerCompetency.Verification.VERIFIED:
        future = competency_future_appointment(competency, profile)
        if future is not None:
            local_start = timezone.localtime(future.scheduled_start)
            raise ValidationError({
                "detail": (
                    f"{competency.therapy.name} cannot be removed because appointment "
                    f"{future.id} is scheduled for {local_start:%d %b %Y at %I:%M %p}. "
                    "Reassign or cancel that appointment first."
                )
            })
    competency.verification_status = PractitionerCompetency.Verification.REJECTED
    competency.verified_by = actor
    competency.verified_at = timezone.now()
    competency.save(update_fields=("verification_status", "verified_by", "verified_at"))
    if profile is not None and profile.staff_profile_id:
        profile.staff_profile.therapy_competencies.remove(competency.therapy)
    PractitionerAuditEvent.objects.create(
        application=competency.application,
        profile=profile,
        organization=(competency.application.organization if competency.application_id else profile.organization),
        actor=actor,
        action="COMPETENCY_REMOVED",
        metadata={"therapy_id": str(competency.therapy_id), "status": "REJECTED"},
    )
    return competency


@transaction.atomic
def set_open_to_work(profile, *, actor, enabled):
    if profile.user_id != actor.id or not profile.is_approved:
        raise PermissionDenied("Open to Work is unavailable.")
    if enabled and profile.staff_profile_id is None:
        raise ValidationError("This category has no operational role yet.")
    if not actor.is_active or not actor.is_enabled or not actor.has_usable_password():
        raise PermissionDenied("Your account must be active and activated.")
    if not RoleAssignment.objects.filter(user=actor, organization=profile.organization,
            role=Role.PHYSIOTHERAPIST, is_active=True,
            organization_membership__is_active=True, clinic_membership__is_active=True,
            clinic__is_active=True).exists():
        raise PermissionDenied("An active therapist role and clinic membership are required.")
    profile.is_open_to_work = enabled
    profile.save(update_fields=("is_open_to_work", "updated_at"))
    PractitionerAuditEvent.objects.create(
        application=getattr(profile, "source_application", None),
        profile=profile, organization=profile.organization, actor=actor,
        action=PractitionerAuditEvent.Action.OPEN_TO_WORK_CHANGED, metadata={"enabled": enabled})
    return profile


def upload_checksum(file):
    digest = hashlib.sha256()
    for chunk in file.chunks():
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()
