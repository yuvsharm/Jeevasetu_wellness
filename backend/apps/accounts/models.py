import uuid

from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.managers import UserManager
from apps.accounts.validators import normalize_email_address, normalize_mobile_number


class Role(models.TextChoices):
    SUPER_ADMIN = "SUPER_ADMIN", "Super administrator"
    ORGANIZATION_ADMIN = "ORGANIZATION_ADMIN", "Organization administrator"
    CLINIC_ADMIN = "CLINIC_ADMIN", "Clinic administrator"
    RECEPTION = "RECEPTION", "Reception"
    THERAPIST = "THERAPIST", "Therapist"
    AYURVEDA_DOCTOR = "AYURVEDA_DOCTOR", "Ayurveda doctor"
    YOGA_TRAINER = "YOGA_TRAINER", "Yoga trainer"
    HOMECARE_EXECUTIVE = "HOMECARE_EXECUTIVE", "Homecare executive"
    PATIENT = "PATIENT", "Patient"


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
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("user", "role"),
                condition=models.Q(organization__isnull=True, clinic__isnull=True),
                name="acct_role_platform_uniq",
            ),
            models.UniqueConstraint(
                fields=("user", "role", "organization"),
                condition=models.Q(organization__isnull=False, clinic__isnull=True),
                name="acct_role_org_uniq",
            ),
            models.UniqueConstraint(
                fields=("user", "role", "clinic"),
                condition=models.Q(clinic__isnull=False),
                name="acct_role_clinic_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=("user", "is_active"), name="acct_role_user_active_idx"),
            models.Index(fields=("organization", "is_active"), name="acct_role_org_active_idx"),
            models.Index(fields=("clinic", "is_active"), name="acct_role_clinic_active_idx"),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.role}"

    def clean(self):
        super().clean()
        if self.clinic_id and self.organization_id != self.clinic.organization_id:
            raise ValidationError("Clinic-scoped roles must use the clinic's organization.")


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
