import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class ApprovalStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    APPROVED = "APPROVED", "Approved"
    REJECTED = "REJECTED", "Rejected"


class AvailabilityRule(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    clinic = models.ForeignKey("tenancy.Clinic", on_delete=models.PROTECT)
    physiotherapist = models.ForeignKey("staff.StaffProfile", on_delete=models.PROTECT)
    weekday = models.PositiveSmallIntegerField()
    starts_at = models.TimeField()
    ends_at = models.TimeField()
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    approval_status = models.CharField(
        max_length=12, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    is_active = models.BooleanField(default=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="availability_rules_submitted",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="availability_rules_reviewed",
    )
    review_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("weekday", "starts_at")
        indexes = [
            models.Index(
                fields=("physiotherapist", "approval_status", "is_active"),
                name="avail_rule_phys_status_idx",
            )
        ]

    def __str__(self):
        return f"{self.physiotherapist_id}:{self.weekday}:{self.starts_at}"

    def clean(self):
        if self.weekday not in range(7):
            raise ValidationError({"weekday": "Use a weekday from 0 to 6."})
        if self.starts_at >= self.ends_at:
            raise ValidationError("Availability must not cross midnight.")
        if self.effective_until and self.effective_until < self.effective_from:
            raise ValidationError("The effective date range is invalid.")
        if self.physiotherapist_id and (
            self.physiotherapist.organization_id != self.organization_id
            or self.physiotherapist.clinic_id != self.clinic_id
        ):
            raise ValidationError("The Physiotherapist is unavailable in this clinic.")


class AvailabilityException(models.Model):
    class Kind(models.TextChoices):
        UNAVAILABLE = "UNAVAILABLE", "Leave or unavailable"
        ADDITIONAL_AVAILABILITY = "ADDITIONAL_AVAILABILITY", "Additional availability"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    clinic = models.ForeignKey("tenancy.Clinic", on_delete=models.PROTECT)
    physiotherapist = models.ForeignKey("staff.StaffProfile", on_delete=models.PROTECT)
    kind = models.CharField(max_length=28, choices=Kind.choices)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    reason = models.CharField(max_length=255)
    approval_status = models.CharField(
        max_length=12, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )
    is_active = models.BooleanField(default=False)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="availability_exceptions_submitted",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="availability_exceptions_reviewed",
    )
    review_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("starts_at",)
        indexes = [
            models.Index(
                fields=("physiotherapist", "approval_status", "is_active", "starts_at"),
                name="avail_exc_phys_status_idx",
            )
        ]

    def __str__(self):
        return f"{self.physiotherapist_id}:{self.kind}:{self.starts_at}"

    def clean(self):
        if self.ends_at <= self.starts_at:
            raise ValidationError("The exception end must follow its start.")
        if self.physiotherapist_id and (
            self.physiotherapist.organization_id != self.organization_id
            or self.physiotherapist.clinic_id != self.clinic_id
        ):
            raise ValidationError("The Physiotherapist is unavailable in this clinic.")


class AvailabilityAuditEvent(models.Model):
    class Action(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        CREATED = "CREATED", "Created"
        EDITED = "EDITED", "Edited"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        DEACTIVATED = "DEACTIVATED", "Deactivated"
        APPROVAL_BLOCKED = "APPROVAL_BLOCKED", "Approval blocked"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    clinic = models.ForeignKey("tenancy.Clinic", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    physiotherapist = models.ForeignKey("staff.StaffProfile", on_delete=models.PROTECT)
    rule = models.ForeignKey(AvailabilityRule, on_delete=models.PROTECT, null=True, blank=True)
    exception = models.ForeignKey(
        AvailabilityException, on_delete=models.PROTECT, null=True, blank=True
    )
    action = models.CharField(max_length=24, choices=Action.choices)
    reason = models.CharField(max_length=255, blank=True)
    rejection_code = models.CharField(max_length=48, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.physiotherapist_id}:{self.action}:{self.created_at}"
