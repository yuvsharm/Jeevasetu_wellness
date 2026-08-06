import hashlib
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
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
    default_duration_minutes = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(30), MaxValueValidator(180)],
    )

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


class ClinicOperatingHours(models.Model):
    clinic = models.OneToOneField(
        "tenancy.Clinic", on_delete=models.PROTECT, related_name="appointment_operating_hours"
    )
    weekdays = models.JSONField(default=list)
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.clinic}:operating-hours"

    def clean(self):
        super().clean()
        if not self.weekdays or any(day not in range(7) for day in self.weekdays):
            raise ValidationError({"weekdays": "Use weekday numbers from 0 to 6."})
        if self.opens_at >= self.closes_at:
            raise ValidationError("Clinic opening time must precede closing time.")


class Appointment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PENDING_ASSIGNMENT = "PENDING_ASSIGNMENT", "Pending assignment"
        SCHEDULED = "SCHEDULED", "Scheduled"
        CONFIRMED = "CONFIRMED", "Confirmed"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        COMPLETED = "COMPLETED", "Completed"
        CANCELLED = "CANCELLED", "Cancelled"
        NO_SHOW = "NO_SHOW", "No show"

    BLOCKING_STATUSES = (Status.SCHEDULED, Status.CONFIRMED, Status.IN_PROGRESS)
    FINAL_STATUSES = (Status.COMPLETED, Status.CANCELLED, Status.NO_SHOW)
    TRANSITIONS = {
        Status.DRAFT: (Status.PENDING_ASSIGNMENT, Status.SCHEDULED),
        Status.PENDING_ASSIGNMENT: (Status.SCHEDULED,),
        Status.SCHEDULED: (Status.CONFIRMED, Status.CANCELLED),
        Status.CONFIRMED: (Status.IN_PROGRESS, Status.CANCELLED, Status.NO_SHOW),
        Status.IN_PROGRESS: (Status.COMPLETED,),
    }

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="appointments"
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic", on_delete=models.PROTECT, related_name="appointments"
    )
    originating_request = models.OneToOneField(
        AppointmentRequest,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="operational_appointment",
    )
    patient = models.ForeignKey(
        "patients.PatientProfile", on_delete=models.PROTECT, related_name="appointments"
    )
    therapy = models.ForeignKey(
        TherapyOption, on_delete=models.PROTECT, related_name="appointments"
    )
    physiotherapist = models.ForeignKey(
        "staff.StaffProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="appointments",
    )
    scheduled_start = models.DateTimeField()
    scheduled_end = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(30), MaxValueValidator(180)]
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=120)
    region = models.CharField(max_length=120)
    pin_code = models.CharField(max_length=6, validators=[RegexValidator(r"^[1-9]\d{5}$")])
    operational_notes = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="created_appointments"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="updated_appointments"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("scheduled_start",)
        indexes = [
            models.Index(
                fields=("organization", "clinic", "scheduled_start"),
                name="appt_sched_org_clinic_time_idx",
            ),
            models.Index(
                fields=("physiotherapist", "scheduled_start"),
                name="appt_sched_physio_time_idx",
            ),
            models.Index(fields=("organization", "status"), name="appt_sched_org_status_idx"),
        ]

    def __str__(self):
        return f"{self.patient.patient_identifier}:{self.scheduled_start}:{self.status}"

    def clean(self):
        super().clean()
        errors = {}
        if self.clinic_id and self.organization_id != self.clinic.organization_id:
            errors["clinic"] = "Clinic is unavailable in this organization."
        if self.patient_id and (
            self.organization_id != self.patient.organization_id
            or self.clinic_id != self.patient.clinic_id
        ):
            errors["patient"] = "Patient is unavailable in this clinic."
        if self.therapy_id and self.organization_id != self.therapy.organization_id:
            errors["therapy"] = "Therapy is unavailable in this organization."
        if self.physiotherapist_id and (
            self.organization_id != self.physiotherapist.organization_id
            or self.clinic_id != self.physiotherapist.clinic_id
        ):
            errors["physiotherapist"] = "Physiotherapist is unavailable in this clinic."
        if self.scheduled_end <= self.scheduled_start:
            errors["scheduled_end"] = "End time must follow start time."
        if errors:
            raise ValidationError(errors)


class AppointmentAuditEvent(models.Model):
    class Event(models.TextChoices):
        CREATED = "CREATED", "Created"
        CONVERTED = "CONVERTED", "Converted"
        RESCHEDULED = "RESCHEDULED", "Rescheduled"
        ASSIGNED = "ASSIGNED", "Assigned"
        REASSIGNED = "REASSIGNED", "Reassigned"
        STATUS_CHANGED = "STATUS_CHANGED", "Status changed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(
        Appointment, on_delete=models.PROTECT, related_name="audit_events"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event = models.CharField(max_length=24, choices=Event.choices)
    previous_status = models.CharField(max_length=24, blank=True)
    new_status = models.CharField(max_length=24, blank=True)
    previous_start = models.DateTimeField(null=True, blank=True)
    new_start = models.DateTimeField(null=True, blank=True)
    previous_physiotherapist = models.ForeignKey(
        "staff.StaffProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="previous_assignment_audits",
    )
    new_physiotherapist = models.ForeignKey(
        "staff.StaffProfile",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="new_assignment_audits",
    )
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.appointment_id}:{self.event}"
