from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.accounts.models import AuthenticationAuditEvent, PasswordResetRequest, RoleAssignment, RoleAuditEvent
from apps.appointments.models import Appointment, AppointmentRating, AppointmentRequestAuditEvent, PractitionerPayment, VisitVerification
from apps.availability.models import AvailabilityAuditEvent, AvailabilityException, AvailabilityRule
from apps.practitioners.models import PractitionerApplication, PractitionerAuditEvent, PractitionerCompetency, PractitionerDocument, PractitionerProfile
from apps.staff.models import StaffDocument, StaffProfile
from apps.tenancy.models import ClinicMembership, OrganizationMembership


def protected_therapist_history(profile: StaffProfile) -> list[str]:
    checks = (
        ("appointments", Appointment.objects.filter(physiotherapist=profile)),
        ("visit records", VisitVerification.objects.filter(physiotherapist=profile)),
        ("payments", PractitionerPayment.objects.filter(physiotherapist=profile)),
        ("customer reviews", AppointmentRating.objects.filter(physiotherapist=profile)),
        ("appointment audit records", AppointmentRequestAuditEvent.objects.filter(physiotherapist=profile)),
        ("assignment audit records", profile.previous_assignment_audits.all() | profile.new_assignment_audits.all()),
    )
    return [label for label, queryset in checks if queryset.exists()]


@transaction.atomic
def permanently_delete_therapist(profile: StaffProfile) -> dict[str, int]:
    protected = protected_therapist_history(profile)
    if protected:
        raise ValidationError({
            "detail": "This therapist has historical records and cannot be permanently deleted. Deactivate the account instead.",
            "protected_records": protected,
        })

    user = profile.user
    organization = profile.organization
    if user.staff_profiles.exclude(pk=profile.pk).exists() or user.patient_profiles.exists():
        raise ValidationError({"detail": "This account has another active profile and cannot be permanently deleted. Deactivate the account instead."})
    if user.created_appointments.exists() or user.updated_appointments.exists() or user.dispatched_appointments.exists() or user.cancelled_appointments.exists():
        raise ValidationError({"detail": "This therapist has historical records and cannot be permanently deleted. Deactivate the account instead."})

    counts: dict[str, int] = {}
    applications = PractitionerApplication.objects.filter(applicant=user, organization=organization)
    app_ids = list(applications.values_list("id", flat=True))
    practitioner_profiles = PractitionerProfile.objects.filter(user=user, organization=organization)
    availability_rules = AvailabilityRule.objects.filter(physiotherapist=profile)
    availability_exceptions = AvailabilityException.objects.filter(physiotherapist=profile)

    for label, queryset in (
        ("availability_audits", AvailabilityAuditEvent.objects.filter(physiotherapist=profile)),
        ("availability_exceptions", availability_exceptions),
        ("availability_rules", availability_rules),
        ("staff_documents", StaffDocument.objects.filter(profile=profile)),
        ("practitioner_audits", PractitionerAuditEvent.objects.filter(application_id__in=app_ids)),
        ("practitioner_documents", PractitionerDocument.objects.filter(application_id__in=app_ids)),
        ("practitioner_competencies", PractitionerCompetency.objects.filter(application_id__in=app_ids)),
        ("practitioner_applications", applications),
        ("practitioner_profiles", practitioner_profiles),
    ):
        counts[label] = queryset.count()
        queryset.delete()

    counts["staff_profiles"] = 1
    profile.delete()

    assignments = RoleAssignment.objects.filter(user=user, organization=organization)
    counts["role_assignments"] = assignments.count()
    assignments.delete()
    counts["role_audits"] = RoleAuditEvent.objects.filter(target_user=user, organization=organization).count()
    RoleAuditEvent.objects.filter(target_user=user, organization=organization).delete()
    counts["authentication_audits"] = AuthenticationAuditEvent.objects.filter(user=user).count()
    AuthenticationAuditEvent.objects.filter(user=user).delete()
    counts["password_reset_requests"] = PasswordResetRequest.objects.filter(user=user).count()
    PasswordResetRequest.objects.filter(user=user).delete()
    user.outstandingtoken_set.all().delete()

    memberships = OrganizationMembership.objects.filter(user=user, organization=organization)
    clinic_memberships = ClinicMembership.objects.filter(organization_membership__in=memberships)
    counts["clinic_memberships"] = clinic_memberships.count()
    clinic_memberships.delete()
    counts["organization_memberships"] = memberships.count()
    memberships.delete()

    if not user.organization_memberships.exists() and not user.role_assignments.exists() and not user.practitioner_profiles.exists() and not user.staff_profiles.exists():
        counts["users"] = 1
        user.delete()
    else:
        counts["users"] = 0
    return counts
