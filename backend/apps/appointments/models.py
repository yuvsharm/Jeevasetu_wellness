import hashlib
import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


class TherapyOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="appointment_therapies"
    )
    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=120)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "slug"), name="appt_therapy_org_slug_uniq"
            )
        ]

    def __str__(self):
        return self.name


class AppointmentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        CANCELLED = "CANCELLED", "Cancelled"

    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Female"
        MALE = "MALE", "Male"
        OTHER = "OTHER", "Other"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    class SessionPreference(models.TextChoices):
        SINGLE = "SINGLE", "Single Session"
        PACKAGE = "PACKAGE", "Package"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="appointment_requests"
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="appointment_requests",
    )
    therapy = models.ForeignKey(
        TherapyOption, on_delete=models.PROTECT, related_name="appointment_requests"
    )
    patient_name = models.CharField(max_length=160)
    age = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(120)]
    )
    gender = models.CharField(max_length=24, choices=Gender.choices)
    mobile_number = models.CharField(
        max_length=10,
        validators=[
            RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")
        ],
    )
    alternate_mobile = models.CharField(
        max_length=10,
        blank=True,
        validators=[
            RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")
        ],
    )
    email = models.EmailField(blank=True)
    session_preference = models.CharField(max_length=12, choices=SessionPreference.choices)
    preferred_date = models.DateField()
    preferred_time = models.TimeField()
    problem_description = models.TextField(max_length=2000)
    pain_area = models.CharField(max_length=160)
    problem_duration = models.CharField(max_length=120)
    doctor_reference = models.CharField(max_length=255, blank=True)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=120)
    pin_code = models.CharField(
        max_length=6,
        validators=[RegexValidator(r"^[1-9]\d{5}$", "Enter a valid 6-digit PIN code.")],
    )
    landmark = models.CharField(max_length=255)
    google_map_link = models.URLField(max_length=500, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    owner_remarks = models.TextField(max_length=1000, blank=True)
    duplicate_fingerprint = models.CharField(max_length=64, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(
                fields=("organization", "status", "created_at"), name="appt_org_status_time_idx"
            ),
            models.Index(fields=("creator", "created_at"), name="appt_creator_time_idx"),
            models.Index(fields=("mobile_number",), name="appt_mobile_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "duplicate_fingerprint"),
                condition=models.Q(status="PENDING"),
                name="appt_pending_fingerprint_uniq",
            )
        ]

    def __str__(self):
        return f"{self.patient_name}:{self.preferred_date}:{self.status}"

    def save(self, *args, **kwargs):
        self.duplicate_fingerprint = self.build_fingerprint()
        super().save(*args, **kwargs)

    def build_fingerprint(self):
        value = "|".join(
            (
                str(self.organization_id),
                self.patient_name.strip().casefold(),
                self.mobile_number,
                str(self.therapy_id),
                str(self.preferred_date),
                str(self.preferred_time)[:5],
            )
        )
        return hashlib.sha256(value.encode()).hexdigest()
