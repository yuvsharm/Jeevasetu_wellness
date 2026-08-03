import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models

tenant_slug_validator = RegexValidator(
    regex=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    message="Use lowercase letters, numbers, and single hyphens only.",
)


class UUIDTimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActiveModel(models.Model):
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class Organization(UUIDTimestampedModel, ActiveModel):
    legal_name = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=63, unique=True, validators=[tenant_slug_validator])
    timezone = models.CharField(max_length=64, blank=True)
    default_currency = models.CharField(max_length=3, blank=True)

    class Meta:
        ordering = ("display_name",)
        indexes = [
            models.Index(fields=("is_active", "slug"), name="tenancy_org_active_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(default_currency="")
                | models.Q(default_currency__regex=r"^[A-Z]{3}$"),
                name="tenancy_org_currency_format",
            ),
        ]

    def __str__(self):
        return self.display_name


class ClinicQuerySet(models.QuerySet):
    def for_organization(self, organization):
        if organization is None:
            return self.none()
        return self.filter(organization=organization)

    def active(self):
        return self.filter(is_active=True, organization__is_active=True)


class Clinic(UUIDTimestampedModel, ActiveModel):
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="clinics",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=63, validators=[tenant_slug_validator])
    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country_code = models.CharField(max_length=2, blank=True)
    timezone = models.CharField(max_length=64, blank=True)

    objects = ClinicQuerySet.as_manager()

    class Meta:
        ordering = ("name",)
        indexes = [
            models.Index(
                fields=("organization", "is_active"),
                name="tenancy_clinic_org_active_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "slug"),
                name="tenancy_clinic_org_slug_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(country_code="") | models.Q(country_code__regex=r"^[A-Z]{2}$"),
                name="tenancy_clinic_country_format",
            ),
        ]

    def __str__(self):
        return f"{self.organization.slug}/{self.slug}"


class OrganizationMembershipQuerySet(models.QuerySet):
    def for_organization(self, organization):
        if organization is None:
            return self.none()
        return self.filter(organization=organization)

    def active(self):
        return self.filter(is_active=True, organization__is_active=True)


class OrganizationMembership(UUIDTimestampedModel, ActiveModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="organization_memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    objects = OrganizationMembershipQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(
                fields=("organization", "is_active"),
                name="tenancy_orgmem_org_active_idx",
            ),
            models.Index(
                fields=("user", "is_active"),
                name="tenancy_orgmem_user_active_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "organization"),
                name="tenancy_orgmem_user_org_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.user_id}:{self.organization.slug}"


class ClinicMembershipQuerySet(models.QuerySet):
    def for_organization(self, organization):
        if organization is None:
            return self.none()
        return self.filter(
            organization_membership__organization=organization,
            clinic__organization=organization,
        )

    def active(self):
        return self.filter(
            is_active=True,
            organization_membership__is_active=True,
            clinic__is_active=True,
            clinic__organization__is_active=True,
        )


class ClinicMembership(UUIDTimestampedModel, ActiveModel):
    organization_membership = models.ForeignKey(
        OrganizationMembership,
        on_delete=models.PROTECT,
        related_name="clinic_memberships",
    )
    clinic = models.ForeignKey(
        Clinic,
        on_delete=models.PROTECT,
        related_name="memberships",
    )

    objects = ClinicMembershipQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(
                fields=("clinic", "is_active"),
                name="tenancy_clinicmem_active_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("organization_membership", "clinic"),
                name="tenancy_clinicmem_member_clinic_uniq",
            ),
        ]

    def __str__(self):
        return f"{self.organization_membership_id}:{self.clinic_id}"

    def clean(self):
        super().clean()
        if (
            self.organization_membership_id
            and self.clinic_id
            and self.organization_membership.organization_id != self.clinic.organization_id
        ):
            raise ValidationError("Clinic and organization membership must share an organization.")
