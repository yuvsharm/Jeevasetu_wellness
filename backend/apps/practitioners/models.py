import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class PractitionerApplication(models.Model):
    class Category(models.TextChoices):
        PHYSIOTHERAPIST = "PHYSIOTHERAPIST", "Physiotherapist"
        WELLNESS = "WELLNESS", "Naturopathy / Wellness Practitioner"

    class Qualification(models.TextChoices):
        BPT = "BPT", "BPT"
        MPT = "MPT", "MPT"
        DPT = "DPT", "DPT"
        OTHER_PHYSIOTHERAPY = "OTHER_PHYSIOTHERAPY", "Other physiotherapy qualification"
        WELLNESS_CERTIFICATION = "WELLNESS_CERTIFICATION", "Wellness qualification/certification"

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        SUBMITTED = "SUBMITTED", "Submitted"
        UNDER_REVIEW = "UNDER_REVIEW", "Under review"
        CORRECTION_REQUIRED = "CORRECTION_REQUIRED", "Correction required"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Female"
        MALE = "MALE", "Male"
        OTHER = "OTHER", "Other"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="practitioner_applications"
    )
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="practitioner_applications"
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic",
        on_delete=models.PROTECT,
        related_name="practitioner_applications",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    category = models.CharField(
        max_length=24, choices=Category.choices, default=Category.PHYSIOTHERAPIST
    )
    full_legal_name = models.CharField(max_length=255, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(
        max_length=24, choices=Gender.choices, default=Gender.PREFER_NOT_TO_SAY
    )
    mobile_number = models.CharField(max_length=16, blank=True)
    alternate_mobile = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    profile_photo = models.FileField(upload_to="practitioners/private/profile/%Y/%m/", blank=True)
    current_address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=120, blank=True)
    state = models.CharField(max_length=120, blank=True, default="Uttar Pradesh")
    pin_code = models.CharField(
        max_length=6, blank=True, validators=[RegexValidator(r"^[1-9]\d{5}$")]
    )
    highest_qualification = models.CharField(
        max_length=32, choices=Qualification.choices, default=Qualification.BPT
    )
    specialization = models.CharField(max_length=160, blank=True)
    college_institute = models.CharField(max_length=255, blank=True)
    awarding_body = models.CharField(max_length=255, blank=True)
    passing_year = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1950), MaxValueValidator(2100)]
    )
    registration_number = models.CharField(max_length=120, blank=True)
    registration_authority = models.CharField(max_length=255, blank=True)
    registration_expiry = models.DateField(null=True, blank=True)
    experience_years = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(80)]
    )
    experience_months = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(11)]
    )
    recent_organization = models.CharField(max_length=255, blank=True)
    previous_experience = models.CharField(max_length=1000, blank=True)
    has_home_service_experience = models.BooleanField(default=False)
    bio = models.TextField(max_length=1500, blank=True)
    languages = models.JSONField(default=list, blank=True)
    availability_notes = models.CharField(max_length=500, blank=True)
    last_completed_step = models.PositiveSmallIntegerField(default=0)
    correction_reason = models.CharField(max_length=500, blank=True)
    rejection_reason = models.CharField(max_length=500, blank=True)
    internal_review_notes = models.TextField(max_length=2000, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_practitioner_applications",
        null=True,
        blank=True,
    )
    approved_profile = models.OneToOneField(
        "PractitionerProfile",
        on_delete=models.PROTECT,
        related_name="source_application",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("organization", "status", "created_at"), name="pract_app_org_status_idx"
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("applicant", "organization"),
                condition=models.Q(
                    status__in=("DRAFT", "SUBMITTED", "UNDER_REVIEW", "CORRECTION_REQUIRED")
                ),
                name="pract_one_open_app_uniq",
            )
        ]

    def __str__(self):
        return f"{self.full_legal_name}:{self.status}"

    def clean(self):
        super().clean()
        errors = {}
        if self.clinic_id and self.clinic.organization_id != self.organization_id:
            errors["clinic"] = "Clinic must belong to the application organization."
        physio_qualifications = {
            self.Qualification.BPT,
            self.Qualification.MPT,
            self.Qualification.DPT,
            self.Qualification.OTHER_PHYSIOTHERAPY,
        }
        if (
            self.category == self.Category.PHYSIOTHERAPIST
            and self.highest_qualification not in physio_qualifications
        ):
            errors["highest_qualification"] = "Select an approved physiotherapy qualification."
        if (
            self.category == self.Category.WELLNESS
            and self.highest_qualification != self.Qualification.WELLNESS_CERTIFICATION
        ):
            errors["highest_qualification"] = "Use a wellness qualification or certification."
        if self.highest_qualification == self.Qualification.MPT and not self.specialization.strip():
            errors["specialization"] = "MPT specialization is required."
        if errors:
            raise ValidationError(errors)


class PractitionerCompetency(models.Model):
    class Verification(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        PractitionerApplication, on_delete=models.PROTECT, related_name="competencies"
    )
    therapy = models.ForeignKey(
        "appointments.TherapyOption",
        on_delete=models.PROTECT,
        related_name="practitioner_competencies",
    )
    experience_months = models.PositiveSmallIntegerField(
        default=0, validators=[MaxValueValidator(960)]
    )
    supporting_certificate = models.FileField(
        upload_to="practitioners/private/competencies/%Y/%m/", blank=True
    )
    verification_status = models.CharField(
        max_length=12, choices=Verification.choices, default=Verification.PENDING
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("application", "therapy"), name="pract_app_therapy_uniq"
            )
        ]

    def __str__(self):
        return f"{self.application_id}:{self.therapy_id}"


class PractitionerDocument(models.Model):
    class Kind(models.TextChoices):
        GOVERNMENT_ID = "GOVERNMENT_ID", "Government identity proof"
        QUALIFICATION = "QUALIFICATION", "Highest qualification certificate"
        DEGREE = "DEGREE", "Degree or diploma"
        REGISTRATION = "REGISTRATION", "Registration or licence"
        EXPERIENCE = "EXPERIENCE", "Experience certificate"
        TRAINING = "TRAINING", "Specialization or training certificate"
        RESUME = "RESUME", "Resume or CV"
        ADDITIONAL = "ADDITIONAL", "Additional certificate"

    class Verification(models.TextChoices):
        PENDING = "PENDING", "Pending"
        VERIFIED = "VERIFIED", "Verified"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        PractitionerApplication, on_delete=models.PROTECT, related_name="documents"
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    file = models.FileField(upload_to="practitioners/private/documents/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.PositiveIntegerField()
    checksum_sha256 = models.CharField(max_length=64)
    verification_status = models.CharField(
        max_length=12, choices=Verification.choices, default=Verification.PENDING
    )
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.application_id}:{self.kind}"


class PractitionerProfile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="practitioner_profiles"
    )
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="practitioner_profiles"
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic",
        on_delete=models.PROTECT,
        related_name="practitioner_profiles",
        null=True,
        blank=True,
    )
    staff_profile = models.OneToOneField(
        "staff.StaffProfile",
        on_delete=models.PROTECT,
        related_name="practitioner_profile",
        null=True,
        blank=True,
    )
    category = models.CharField(max_length=24, choices=PractitionerApplication.Category.choices)
    qualification_specialization = models.CharField(max_length=160, blank=True)
    is_approved = models.BooleanField(default=True)
    is_publicly_visible = models.BooleanField(default=False)
    is_open_to_work = models.BooleanField(default=False)
    approved_at = models.DateTimeField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(
                fields=("is_approved", "is_publicly_visible", "is_open_to_work"),
                name="pract_profile_state_idx",
            )
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("user", "organization"), name="pract_profile_user_org_uniq"
            )
        ]

    def __str__(self):
        return f"{self.user_id}:{self.category}"


class PractitionerAuditEvent(models.Model):
    class Action(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        REVIEW_STARTED = "REVIEW_STARTED", "Review started"
        CORRECTION_REQUESTED = "CORRECTION_REQUESTED", "Correction requested"
        RESUBMITTED = "RESUBMITTED", "Resubmitted"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"
        DOCUMENT_VERIFIED = "DOCUMENT_VERIFIED", "Document verified"
        COMPETENCY_VERIFIED = "COMPETENCY_VERIFIED", "Competency verified"
        OPEN_TO_WORK_CHANGED = "OPEN_TO_WORK_CHANGED", "Open to work changed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        PractitionerApplication, on_delete=models.PROTECT, related_name="audit_events"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"{self.application_id}:{self.action}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Practitioner audit events are immutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Practitioner audit events are immutable.")
