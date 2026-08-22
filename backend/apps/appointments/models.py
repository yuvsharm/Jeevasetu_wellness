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
    family_member = models.ForeignKey(
        "patients.CustomerFamilyMember", on_delete=models.PROTECT, null=True, blank=True,
        related_name="appointment_requests",
    )
    therapy = models.ForeignKey(
        TherapyOption, on_delete=models.PROTECT, related_name="appointment_requests"
    )
    requested_therapies = models.ManyToManyField(
        TherapyOption, related_name="multi_therapy_requests", blank=True
    )
    preferred_practitioner = models.ForeignKey(
        "practitioners.PractitionerProfile",
        on_delete=models.PROTECT,
        related_name="preferred_appointment_requests",
        null=True,
        blank=True,
        help_text="Customer preference only; never an operational assignment.",
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

    @property
    def requested_duration_minutes(self):
        return (1 + self.requested_therapies.count()) * 45


class BookingPhoneVerification(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="booking_phone_verifications"
    )
    mobile_number = models.CharField(
        max_length=10,
        validators=[RegexValidator(r"^[6-9]\d{9}$", "Enter a valid 10-digit Indian mobile number.")],
    )
    otp_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    failed_attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=("organization", "mobile_number", "created_at"), name="appt_booking_otp_lookup_idx")]


class ClinicOperatingHours(models.Model):
    clinic = models.OneToOneField(
        "tenancy.Clinic", on_delete=models.PROTECT, related_name="appointment_operating_hours"
    )
    weekdays = models.JSONField(default=list)
    opens_at = models.TimeField()
    closes_at = models.TimeField()
    is_active = models.BooleanField(default=True)
    cancellation_cutoff_minutes = models.PositiveSmallIntegerField(default=120)
    rescheduling_cutoff_minutes = models.PositiveSmallIntegerField(default=120)
    maximum_reschedules = models.PositiveSmallIntegerField(default=3)
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
    class JourneyStatus(models.TextChoices):
        NOT_STARTED = "NOT_STARTED", "Not started"
        EN_ROUTE = "EN_ROUTE", "En route"
        ARRIVED = "ARRIVED", "Arrived"

    class AssignmentStatus(models.TextChoices):
        UNASSIGNED = "UNASSIGNED", "Unassigned"
        PENDING = "PENDING", "Pending response"
        ACCEPTED = "ACCEPTED", "Accepted"
        REJECTED = "REJECTED", "Rejected by Physiotherapist"

    class CancellationCategory(models.TextChoices):
        CUSTOMER_REQUEST = "CUSTOMER_REQUEST", "Customer request"
        PHYSIOTHERAPIST_UNAVAILABLE = (
            "PHYSIOTHERAPIST_UNAVAILABLE",
            "Physiotherapist unavailable",
        )
        CLINIC_OPERATIONAL_ISSUE = "CLINIC_OPERATIONAL_ISSUE", "Clinic operational issue"
        SCHEDULING_CONFLICT = "SCHEDULING_CONFLICT", "Scheduling conflict"
        DUPLICATE_APPOINTMENT = "DUPLICATE_APPOINTMENT", "Duplicate appointment"
        OTHER = "OTHER", "Other"

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
        validators=[MinValueValidator(30), MaxValueValidator(360)]
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    landmark = models.CharField(max_length=160, blank=True)
    city = models.CharField(max_length=120)
    region = models.CharField(max_length=120)
    pin_code = models.CharField(max_length=6, validators=[RegexValidator(r"^[1-9]\d{5}$")])
    operational_notes = models.CharField(max_length=500, blank=True)
    manager_remarks = models.CharField(max_length=500, blank=True)
    assignment_status = models.CharField(
        max_length=16, choices=AssignmentStatus.choices, default=AssignmentStatus.UNASSIGNED
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dispatched_appointments",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    assignment_responded_at = models.DateTimeField(null=True, blank=True)
    assignment_rejection_reason = models.CharField(max_length=255, blank=True)
    journey_status = models.CharField(
        max_length=16, choices=JourneyStatus.choices, default=JourneyStatus.NOT_STARTED
    )
    en_route_at = models.DateTimeField(null=True, blank=True)
    arrived_at = models.DateTimeField(null=True, blank=True)
    service_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    shared_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    shared_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    location_shared_at = models.DateTimeField(null=True, blank=True)
    reschedule_count = models.PositiveSmallIntegerField(default=0)
    cancellation_category = models.CharField(
        max_length=32, choices=CancellationCategory.choices, blank=True
    )
    cancellation_reason = models.CharField(max_length=255, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cancelled_appointments",
    )
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
        UNASSIGNED = "UNASSIGNED", "Assignment cancelled"
        ASSIGNMENT_ACCEPTED = "ASSIGNMENT_ACCEPTED", "Assignment accepted"
        ASSIGNMENT_REJECTED = "ASSIGNMENT_REJECTED", "Assignment rejected"
        CUSTOMER_CHANGE_REQUESTED = "CUSTOMER_CHANGE_REQUESTED", "Customer change requested"
        STATUS_CHANGED = "STATUS_CHANGED", "Status changed"
        CANCELLED = "CANCELLED", "Cancelled"
        RESCHEDULE_REJECTED = "RESCHEDULE_REJECTED", "Reschedule rejected"
        CANCELLATION_REJECTED = "CANCELLATION_REJECTED", "Cancellation rejected"
        JOURNEY_STATUS_CHANGED = "JOURNEY_STATUS_CHANGED", "Journey status changed"
        LOCATION_SHARED = "LOCATION_SHARED", "Location shared"
        RATING_SUBMITTED = "RATING_SUBMITTED", "Rating submitted"
        PAYMENT_STATUS_CHANGED = "PAYMENT_STATUS_CHANGED", "Payment status changed"

    class Outcome(models.TextChoices):
        SUCCEEDED = "SUCCEEDED", "Succeeded"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(
        Appointment, on_delete=models.PROTECT, related_name="audit_events"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    event = models.CharField(max_length=32, choices=Event.choices)
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
    reason_category = models.CharField(max_length=32, blank=True)
    outcome = models.CharField(max_length=12, choices=Outcome.choices, default=Outcome.SUCCEEDED)
    override_used = models.BooleanField(default=False)
    override_reason = models.CharField(max_length=255, blank=True)
    rejection_code = models.CharField(max_length=48, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.appointment_id}:{self.event}"


class AppointmentChangeRequest(models.Model):
    class Kind(models.TextChoices):
        RESCHEDULE = "RESCHEDULE", "Reschedule"
        CANCELLATION = "CANCELLATION", "Cancellation"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"
        WITHDRAWN = "WITHDRAWN", "Withdrawn"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(
        Appointment, on_delete=models.PROTECT, related_name="change_requests"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    requested_start = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("appointment", "kind"),
                condition=models.Q(status="PENDING"),
                name="appt_pending_change_kind_uniq",
            )
        ]

    def __str__(self):
        return f"{self.appointment_id}:{self.kind}:{self.status}"


class VisitVerification(models.Model):
    class State(models.TextChoices):
        AWAITING = "AWAITING", "Awaiting verification"
        VERIFIED = "VERIFIED", "Verified check-in"
        EXPIRED = "EXPIRED", "Expired"
        LOCKED = "LOCKED", "Locked"
        INVALIDATED = "INVALIDATED", "Invalidated"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(
        Appointment, on_delete=models.PROTECT, related_name="visit_verifications"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    customer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="customer_visit_verifications",
    )
    physiotherapist = models.ForeignKey(
        "staff.StaffProfile", on_delete=models.PROTECT, related_name="visit_verifications"
    )
    state = models.CharField(max_length=16, choices=State.choices, default=State.AWAITING)
    otp_hash = models.CharField(max_length=255)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True, blank=True)
    failed_attempt_count = models.PositiveSmallIntegerField(default=0)
    max_attempts = models.PositiveSmallIntegerField(default=5)
    locked_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)
    invalidation_reason = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=("appointment", "state"), name="appt_visit_verify_state_idx"),
            models.Index(fields=("organization", "created_at"), name="appt_visit_verify_org_idx"),
        ]

    def __str__(self):
        return f"{self.appointment_id}:{self.state}"


class VisitVerificationAuditEvent(models.Model):
    class Event(models.TextChoices):
        ISSUED = "ISSUED", "OTP issued"
        REISSUED = "REISSUED", "OTP reissued"
        ATTEMPTED = "ATTEMPTED", "Verification attempted"
        SUCCEEDED = "SUCCEEDED", "Verification succeeded"
        EXPIRED = "EXPIRED", "OTP expired"
        INVALIDATED = "INVALIDATED", "OTP invalidated"
        LOCKED = "LOCKED", "OTP locked"
        UNAUTHORIZED = "UNAUTHORIZED", "Unauthorized attempt"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification = models.ForeignKey(
        VisitVerification, on_delete=models.PROTECT, related_name="audit_events"
    )
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="visit_verification_audits",
    )
    event = models.CharField(max_length=16, choices=Event.choices)
    outcome = models.CharField(max_length=16, blank=True)
    reason_code = models.CharField(max_length=48, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"{self.verification_id}:{self.event}"


class AppointmentRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(Appointment, on_delete=models.PROTECT, related_name="rating")
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    physiotherapist = models.ForeignKey("staff.StaffProfile", on_delete=models.PROTECT)
    stars = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.CharField(max_length=1000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PractitionerPayment(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        PAID = "PAID", "Paid"
        HELD = "HELD", "Held / disputed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.OneToOneField(Appointment, on_delete=models.PROTECT, related_name="practitioner_payment")
    organization = models.ForeignKey("tenancy.Organization", on_delete=models.PROTECT)
    physiotherapist = models.ForeignKey("staff.StaffProfile", on_delete=models.PROTECT)
    payable_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    paid_at = models.DateTimeField(null=True, blank=True)
    reference = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=500, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
