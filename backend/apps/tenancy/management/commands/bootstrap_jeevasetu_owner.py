from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, RoleAssignment, RoleAuditEvent
from apps.accounts.role_policy import record_role_event
from apps.accounts.validators import normalize_email_address
from apps.tenancy.models import (
    Clinic,
    ClinicMembership,
    Organization,
    OrganizationMembership,
)

ORGANIZATION = {
    "legal_name": "JeevaSetu Wellness",
    "display_name": "JeevaSetu Wellness",
    "slug": "jeevasetu-wellness",
    "timezone": "Asia/Kolkata",
    "default_currency": "INR",
}
CLINIC = {
    "name": "JeevaSetu Wellness Meerut",
    "slug": "meerut",
    "timezone": "Asia/Kolkata",
}


class Command(BaseCommand):
    help = "Create the first JeevaSetu development tenant and Owner access idempotently."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True, help="Email of an existing registered user.")

    def handle(self, *args, **options):
        email = normalize_email_address(options["email"])
        user_model = get_user_model()

        with transaction.atomic():
            try:
                user = user_model.objects.select_for_update().get(email__iexact=email)
            except user_model.DoesNotExist as error:
                raise CommandError(f"No registered user exists for {email}.") from error
            if not user.is_active or not user.is_enabled:
                raise CommandError("The registered user must be active and enabled.")

            organization, organization_created = Organization.objects.get_or_create(
                slug=ORGANIZATION["slug"],
                defaults=ORGANIZATION,
            )
            organization_changed = self._apply_values(
                organization,
                {**ORGANIZATION, "is_active": True},
            )

            clinic, clinic_created = Clinic.objects.get_or_create(
                organization=organization,
                slug=CLINIC["slug"],
                defaults=CLINIC,
            )
            clinic_changed = self._apply_values(clinic, {**CLINIC, "is_active": True})

            membership, membership_created = OrganizationMembership.objects.get_or_create(
                user=user,
                organization=organization,
                defaults={"is_active": True},
            )
            membership_changed = self._apply_values(membership, {"is_active": True})

            clinic_membership, clinic_membership_created = ClinicMembership.objects.get_or_create(
                organization_membership=membership,
                clinic=clinic,
                defaults={"is_active": True},
            )
            clinic_membership_changed = self._apply_values(
                clinic_membership,
                {"is_active": True},
            )

            role_assignment, role_state = self._owner_assignment(
                user=user,
                organization=organization,
                membership=membership,
            )
            if role_state != "existing":
                record_role_event(
                    (
                        RoleAuditEvent.Event.ASSIGNED
                        if role_state == "created"
                        else RoleAuditEvent.Event.ACTIVATED
                    ),
                    actor=None,
                    target=user,
                    organization=organization,
                    new_role=Role.OWNER,
                    metadata={"source": "bootstrap_jeevasetu_owner"},
                )

        created = sum(
            (
                organization_created,
                clinic_created,
                membership_created,
                clinic_membership_created,
                role_state == "created",
            )
        )
        updated = sum(
            (
                organization_changed,
                clinic_changed,
                membership_changed,
                clinic_membership_changed,
                role_state == "reactivated",
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"JeevaSetu Owner bootstrap complete for {email}: "
                f"created={created}, updated={updated}, "
                f"organization={organization.slug}, clinic={clinic.slug}, "
                f"role={role_assignment.role}."
            )
        )

    @staticmethod
    def _apply_values(instance, values):
        changed_fields = []
        for field, value in values.items():
            if getattr(instance, field) != value:
                setattr(instance, field, value)
                changed_fields.append(field)
        instance.full_clean()
        if changed_fields:
            instance.save(update_fields=(*changed_fields, "updated_at"))
        return bool(changed_fields)

    @staticmethod
    def _owner_assignment(*, user, organization, membership):
        active = RoleAssignment.objects.filter(
            user=user,
            organization=organization,
            role=Role.OWNER,
            clinic__isnull=True,
            is_active=True,
        ).first()
        if active:
            changed_fields = []
            if active.organization_membership_id != membership.id:
                active.organization_membership = membership
                changed_fields.append("organization_membership")
            if changed_fields:
                active.full_clean()
                active.save(update_fields=(*changed_fields, "updated_at"))
            return active, "existing"

        assignment = (
            RoleAssignment.objects.filter(
                user=user,
                organization=organization,
                role=Role.OWNER,
                clinic__isnull=True,
                is_active=False,
            )
            .order_by("-updated_at")
            .first()
        )
        state = "reactivated" if assignment else "created"
        if assignment is None:
            assignment = RoleAssignment(
                user=user,
                organization=organization,
                role=Role.OWNER,
            )
        assignment.organization_membership = membership
        assignment.clinic = None
        assignment.clinic_membership = None
        assignment.is_active = True
        assignment.disabled_at = None
        assignment.disabled_reason = ""
        assignment.full_clean()
        assignment.save()
        return assignment, state
