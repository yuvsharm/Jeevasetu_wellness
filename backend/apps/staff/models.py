import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, RegexValidator
from django.db import models


class Specialization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class ServiceArea(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="service_areas"
    )
    name = models.CharField(max_length=120)
    pin_codes = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ("name",)
        constraints = [
            models.UniqueConstraint(
                fields=("organization", "name"), name="staff_area_org_name_uniq"
            )
        ]

    def __str__(self):
        return self.name


class StaffProfile(models.Model):
    class Gender(models.TextChoices):
        FEMALE = "FEMALE", "Female"
        MALE = "MALE", "Male"
        OTHER = "OTHER", "Other"
        PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY", "Prefer not to say"

    class Availability(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Available"
        BUSY = "BUSY", "Busy"
        UNAVAILABLE = "UNAVAILABLE", "Unavailable"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="staff_profiles"
    )
    organization = models.ForeignKey(
        "tenancy.Organization", on_delete=models.PROTECT, related_name="staff_profiles"
    )
    clinic = models.ForeignKey(
        "tenancy.Clinic",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="staff_profiles",
    )
    staff_type = models.CharField(
        max_length=32, choices=(("MANAGER", "Manager"), ("PHYSIOTHERAPIST", "Physiotherapist"))
    )
    profile_photo = models.FileField(upload_to="staff/profile-photos/%Y/%m/", blank=True)
    gender = models.CharField(max_length=24, choices=Gender.choices)
    date_of_birth = models.DateField()
    qualification = models.CharField(max_length=255)
    registration_number = models.CharField(max_length=120, blank=True)
    experience_years = models.PositiveSmallIntegerField(validators=[MaxValueValidator(80)])
    specializations = models.ManyToManyField(
        Specialization, blank=True, related_name="staff_profiles"
    )
    languages_known = models.JSONField(default=list)
    alternate_mobile = models.CharField(
        max_length=10, blank=True, validators=[RegexValidator(r"^[6-9]\d{9}$")]
    )
    emergency_contact = models.CharField(
        max_length=10, validators=[RegexValidator(r"^[6-9]\d{9}$")]
    )
    current_address = models.CharField(max_length=500)
    city = models.CharField(max_length=120)
    pin_code = models.CharField(max_length=6, validators=[RegexValidator(r"^[1-9]\d{5}$")])
    service_areas = models.ManyToManyField(ServiceArea, blank=True, related_name="staff_profiles")
    availability = models.CharField(
        max_length=16, choices=Availability.choices, default=Availability.UNAVAILABLE
    )
    is_online = models.BooleanField(default=False)
    joining_date = models.DateField()
    bio = models.TextField(max_length=2000, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user__first_name", "user__last_name")
        constraints = [
            models.UniqueConstraint(fields=("user", "organization"), name="staff_user_org_uniq")
        ]
        indexes = [models.Index(fields=("organization", "staff_type"), name="staff_org_type_idx")]

    def __str__(self):
        return f"{self.user.get_full_name()}:{self.staff_type}"


class StaffDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(StaffProfile, on_delete=models.PROTECT, related_name="documents")
    label = models.CharField(max_length=120)
    file = models.FileField(upload_to="staff/documents/%Y/%m/")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.label
