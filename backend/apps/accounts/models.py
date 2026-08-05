import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.managers import UserManager
from apps.accounts.validators import normalize_email_address, normalize_mobile_number


class Role(models.TextChoices):
    OWNER = "OWNER", "Owner"
    MANAGER = "MANAGER", "Manager"
    PHYSIOTHERAPIST = "PHYSIOTHERAPIST", "Physiotherapist"
    CUSTOMER = "CUSTOMER", "Customer"


class User(AbstractUser):
    """UUID identity used by authentication and future domain modules."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    mobile_number = models.CharField(max_length=16, unique=True, null=True, blank=True)
    is_enabled = models.BooleanField(default=True)
    profile_image = models.URLField(max_length=500, blank=True)

    objects = UserManager()

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~models.Q(email=""),
                name="accounts_user_email_ci_uniq",
            )
        ]
        indexes = [
            models.Index(
                fields=("mobile_number", "is_active", "is_enabled"),
                name="acct_user_mobile_state_idx",
            ),
            models.Index(
                fields=("email", "is_active", "is_enabled"), name="acct_user_email_state_idx"
            ),
        ]

    def clean(self):
        super().clean()
        self.email = normalize_email_address(self.email)
        if self.mobile_number:
            self.mobile_number = normalize_mobile_number(self.mobile_number)


class RoleAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="role_assignments")
    role = models.CharField(max_length=32, choices=Role.choices)
    organization = models.ForeignKey(
        "tenancy.Organization",
        on_delete=models.PROTECT,
        related_name="role_assignments",
    )
    organization_membership = models.ForeignKey(
        "tenancy.OrganizationMembership",
        on_delete=models.PROTECT,
        related_name="role_assignments",
        null=True,
        blank=True,
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic",
        on_delete=models.PROTECT,
        related_name="role_assignments",
        null=True,
        blank=True,
    )
    clinic_membership = models.ForeignKey(
        "tenancy.ClinicMembership",
        on_delete=models.PROTECT,
        related_name="role_assignments",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        related_name="assigned_role_assignments",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    disabled_at = models.DateTimeField(null=True, blank=True)
    disabled_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role", "organization"),
                condition=models.Q(is_active=True, clinic__isnull=True),
                name="acct_role_active_org_uniq",
            ),
            models.UniqueConstraint(
                fields=("user", "role", "organization", "clinic"),
                condition=models.Q(is_active=True, clinic__isnull=False),
                name="acct_role_active_clinic_uniq",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(is_active=True, disabled_at__isnull=True) | models.Q(is_active=False)
                ),
                name="acct_role_active_not_disabled",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(role=Role.OWNER)
                    | models.Q(clinic__isnull=True, clinic_membership__isnull=True)
                ),
                name="acct_role_owner_org_scope",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(role=Role.PHYSIOTHERAPIST)
                    | models.Q(clinic__isnull=False, clinic_membership__isnull=False)
                ),
                name="acct_role_physio_clinic_scope",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "is_active"), name="acct_role_user_active_idx"),
            models.Index(fields=("organization", "is_active"), name="acct_role_org_active_idx"),
            models.Index(fields=("clinic", "is_active"), name="acct_role_clinic_active_idx"),
            models.Index(fields=("role", "is_active"), name="acct_role_kind_active_idx"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.role}"

    def clean(self):
        super().clean()
        errors = {}
        if self.organization_membership_id:
            membership = self.organization_membership
            if self.user_id != membership.user_id:
                errors["user"] = "User must match the organization membership."
            if self.organization_id != membership.organization_id:
                errors["organization"] = "Role and membership organizations must match."
        else:
            errors["organization_membership"] = "Organization membership is required."
        if self.clinic_id and self.organization_id != self.clinic.organization_id:
            errors["clinic"] = "Clinic must belong to the role organization."
        if self.clinic_membership_id:
            clinic_membership = self.clinic_membership
            if clinic_membership.organization_membership_id != self.organization_membership_id:
                errors["clinic_membership"] = "Clinic membership must belong to the member."
            if clinic_membership.clinic_id != self.clinic_id:
                errors["clinic_membership"] = "Clinic membership must match the role clinic."
        if self.role == Role.OWNER and self.clinic_id:
            errors["clinic"] = "Owner is organization scoped."
        if self.role == Role.PHYSIOTHERAPIST and not self.clinic_id:
            errors["clinic"] = "Physiotherapist is clinic scoped."
        if self.clinic_id and not self.clinic_membership_id:
            errors["clinic_membership"] = "Clinic-scoped roles require clinic membership."
        if not self.is_active and self.disabled_at is None:
            errors["disabled_at"] = "Disabled roles require a timestamp."
        if self.is_active and (self.disabled_at or self.disabled_reason):
            errors["is_active"] = "Active roles cannot contain disable metadata."
        if errors:
            raise ValidationError(errors)


class RoleAuditEvent(models.Model):
    class Event(models.TextChoices):
        ASSIGNED = "ROLE_ASSIGNED", "Role assigned"
        CHANGED = "ROLE_CHANGED", "Role changed"
        ACTIVATED = "ROLE_ACTIVATED", "Role activated"
        DISABLED = "ROLE_DISABLED", "Role disabled"
        PRIVILEGE_ESCALATION = "PRIVILEGE_ESCALATION", "Privilege escalation attempted"
        CROSS_TENANT = "CROSS_TENANT", "Cross-tenant role operation attempted"
        FINAL_OWNER = "FINAL_OWNER", "Final-owner protection attempted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.CharField(max_length=32, choices=Event.choices)
    acting_user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="role_audit_actions", null=True, blank=True
    )
    target_user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name="role_audit_targets", null=True, blank=True
    )
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="role_audit_events"
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="role_audit_events",
    )
    old_role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    new_role = models.CharField(max_length=32, choices=Role.choices, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("organization", "created_at"), name="acct_rbaudit_org_time_idx"),
            models.Index(fields=("event", "created_at"), name="acct_rbaudit_event_time_idx"),
        ]

    def __str__(self):
        return f"{self.event}:{self.organization_id}:{self.id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Role audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Role audit events are immutable.")


class PasswordResetRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="password_reset_requests")
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=("user", "used_at", "expires_at"), name="acct_reset_user_state_idx")
        ]

    def __str__(self):
        return f"{self.user_id}:{self.id}"


class AuthenticationAuditEvent(models.Model):
    class Event(models.TextChoices):
        REGISTRATION = "REGISTRATION", "Registration"
        LOGIN = "LOGIN", "Login"
        REFRESH = "REFRESH", "Token refresh"
        LOGOUT = "LOGOUT", "Logout"
        PASSWORD_CHANGE = "PASSWORD_CHANGE", "Password change"
        PASSWORD_RESET_REQUEST = "PASSWORD_RESET_REQUEST", "Password reset request"
        PASSWORD_RESET_COMPLETE = "PASSWORD_RESET_COMPLETE", "Password reset complete"
        PROFILE_UPDATE = "PROFILE_UPDATE", "Profile update"

    class Outcome(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FAILURE = "FAILURE", "Failure"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event = models.CharField(max_length=32, choices=Event.choices)
    outcome = models.CharField(max_length=8, choices=Outcome.choices)
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="authentication_audit_events",
        null=True,
        blank=True,
    )
    identifier_hash = models.CharField(max_length=64, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("event", "outcome", "created_at"), name="acct_audit_event_time_idx"
            ),
            models.Index(fields=("user", "created_at"), name="acct_audit_user_time_idx"),
        ]

    def __str__(self):
        return f"{self.event}:{self.outcome}:{self.id}"
