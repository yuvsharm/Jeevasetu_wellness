import uuid
from datetime import date

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models, transaction

mobile_validator = RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")
pin_validator = RegexValidator(r"^[1-9]\d{5}$", "Enter a valid 6-digit PIN code.")


def validate_photo_size(value):
    if value.size > 2 * 1024 * 1024:
        raise ValidationError("Profile photographs must not exceed 2 MB.")


class PatientSequence(models.Model):
    organization = models.OneToOneField(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="patient_sequence"
    )
    next_value = models.PositiveBigIntegerField(default=1)

    def __str__(self):
        return f"{self.organization.slug}:{self.next_value}"

    @classmethod
    def issue(cls, organization):
        with transaction.atomic():
            type(organization).objects.select_for_update().get(pk=organization.pk)
            sequence, _ = cls.objects.select_for_update().get_or_create(organization=organization)
            value = sequence.next_value
            sequence.next_value += 1
            sequence.save(update_fields=("next_value",))
        return f"PAT-{value:06d}"


class PatientProfile(models.Model):  # noqa: DJ012
    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Female"
        MALE = "MALE", "Male"
        OTHER = "OTHER", "Other"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="patient_profiles"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="patient_profiles",
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic", on_delete=models.PROTECT, related_name="patient_profiles"
    )
    patient_identifier = models.CharField(max_length=16, editable=False)
    full_name = models.CharField(max_length=160)
    mobile_number = models.CharField(max_length=10, validators=[mobile_validator])
    email = models.EmailField(blank=True)
    gender = models.CharField(max_length=24, choices=Gender.choices)
    date_of_birth = models.DateField(null=True, blank=True)
    age = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(0), MaxValueValidator(120)]
    )
    profile_photo = models.FileField(
        upload_to="patients/profile-photos/%Y/%m/",
        blank=True,
        validators=[FileExtensionValidator(("jpg", "jpeg", "png", "webp")), validate_photo_size],
    )
    emergency_contact_name = models.CharField(max_length=160)
    emergency_contact_relationship = models.CharField(max_length=80)
    emergency_contact_mobile = models.CharField(max_length=10, validators=[mobile_validator])
    guardian_name = models.CharField(max_length=160, blank=True)
    guardian_relationship = models.CharField(max_length=80, blank=True)
    guardian_mobile = models.CharField(max_length=10, blank=True, validators=[mobile_validator])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "patient_identifier"), name="patient_org_identifier_uniq"
            ),
            models.UniqueConstraint(
                fields=("organization", "user"),
                condition=models.Q(user__isnull=False),
                name="patient_org_user_uniq",
            ),
            models.UniqueConstraint(
                fields=("organization", "mobile_number"),
                condition=models.Q(is_active=True),
                name="patient_active_org_mobile_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(date_of_birth__isnull=False) | models.Q(age__isnull=False),
                name="patient_dob_or_age_required",
            ),
        ]
        indexes = [
            models.Index(
                fields=("organization", "clinic", "is_active"),
                name="patient_org_clinic_status_idx",
            ),
            models.Index(fields=("organization", "full_name"), name="patient_org_name_idx"),
        ]

    def __str__(self):
        return f"{self.patient_identifier}:{self.full_name}"

    def save(self, *args, **kwargs):
        if not self.patient_identifier:
            self.patient_identifier = PatientSequence.issue(self.organization)
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        if self.clinic_id and self.organization_id != self.clinic.organization_id:
            raise ValidationError("Clinic is unavailable in this organization.")
        if self.date_of_birth and self.date_of_birth > date.today():
            raise ValidationError({"date_of_birth": "Date of birth cannot be in the future."})
        calculated_age = self.age
        if self.date_of_birth:
            today = date.today()
            calculated_age = (
                today.year
                - self.date_of_birth.year
                - ((today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day))
            )
        if calculated_age is not None and calculated_age < 18:
            if not all((self.guardian_name, self.guardian_relationship, self.guardian_mobile)):
                raise ValidationError("Parent or legal guardian details are required for minors.")


class CustomerFamilyMember(models.Model):
    """A care recipient owned by a customer account, not another login identity."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT, related_name="customer_family_members")
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="family_members")
    full_name = models.CharField(max_length=160)
    age = models.PositiveSmallIntegerField(validators=[MinValueValidator(0), MaxValueValidator(120)])
    gender = models.CharField(max_length=24, choices=PatientProfile.Gender.choices)
    relationship = models.CharField(max_length=80)
    relevant_details = models.TextField(max_length=2000, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("full_name",)
        indexes = [models.Index(fields=("organization", "customer", "is_active"), name="patient_family_owner_idx")]

    def clean(self):
        super().clean()
        if self.customer_id and self.organization_id and not self.customer.organization_memberships.filter(organization=self.organization, is_active=True).exists():
            raise ValidationError("Family member owner is unavailable in this organization.")


class PatientAddress(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(PatientProfile, on_delete=models.PROTECT, related_name="addresses")
    label = models.CharField(max_length=80, default="Home")
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=120)
    region = models.CharField(max_length=120)
    pin_code = models.CharField(max_length=6, validators=[pin_validator])
    is_primary = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-is_primary", "created_at")
        constraints = [
            models.UniqueConstraint(
                fields=("patient",),
                condition=models.Q(is_primary=True, is_active=True),
                name="patient_one_primary_address",
            )
        ]

    def __str__(self):
        return f"{self.patient.patient_identifier}:{self.label}"

    def clean(self):
        super().clean()
        active = PatientAddress.objects.filter(patient=self.patient, is_active=True).exclude(
            pk=self.pk
        )
        if self.is_active and active.count() >= 4:
            raise ValidationError(
                "A patient may have one primary and up to three additional addresses."
            )


class CaregiverRelationship(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(PatientProfile, on_delete=models.PROTECT, related_name="caregivers")
    full_name = models.CharField(max_length=160)
    relationship = models.CharField(max_length=80)
    mobile_number = models.CharField(max_length=10, validators=[mobile_validator])
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.patient.patient_identifier}:{self.full_name}"


class PatientStatusAudit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        PatientProfile, on_delete=models.PROTECT, related_name="status_audits"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    previous_status = models.BooleanField()
    new_status = models.BooleanField()
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.patient.patient_identifier}:{self.previous_status}->{self.new_status}"
