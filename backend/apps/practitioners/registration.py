"""Complete self-application using Owner field validation and the existing OTP proof."""
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser

from apps.accounts.models import User
from apps.accounts.throttling import CustomerRegistrationRateThrottle
from apps.appointments.booking_verification import resolve_booking_verification
from apps.appointments.models import TherapyOption
from apps.staff.models import ServiceArea
from apps.staff.serializers import StaffCreateSerializer
from apps.staff.views import StaffMobileAvailabilityView
from apps.tenancy.models import Clinic, OrganizationMembership
from .models import PractitionerApplication, PractitionerCompetency
from .serializers import DocumentUploadSerializer
from .services import submit_application


class CompleteApplicationSerializer(StaffCreateSerializer):
    working_days = serializers.JSONField()
    working_hours_start = serializers.TimeField()
    working_hours_end = serializers.TimeField()
    specialization = serializers.CharField(max_length=160, required=False, allow_blank=True)

    class Meta(StaffCreateSerializer.Meta):
        fields = StaffCreateSerializer.Meta.fields + ("working_days", "working_hours_start", "working_hours_end", "specialization")

    def validate(self, attrs):
        attrs = super().validate(attrs)
        for name, label in (("profile_photo", "Profile Photograph"), ("government_id_document", "Government Identity Proof"),
                            ("qualification_document", "Qualification Certificate"), ("password", "Password"),
                            ("mobile_verification_token", "Mobile verification"), ("clinic", "Clinic"),
                            ("service_areas", "Service area"), ("therapy_competencies", "Therapy competency"),
                            ("languages_known", "Languages"), ("qualification", "Qualification")):
            if not attrs.get(name):
                raise serializers.ValidationError({name: f"{label} is required."})
        if attrs["staff_type"] != "PHYSIOTHERAPIST":
            raise serializers.ValidationError("Select a practitioner type.")
        if attrs["working_hours_start"] >= attrs["working_hours_end"]:
            raise serializers.ValidationError({"working_hours_end": "Working hours must end after they start."})
        days = attrs["working_days"]
        if not isinstance(days, list) or not days or any(type(day) is not int or day not in range(7) for day in days):
            raise serializers.ValidationError({"working_days": "Select valid working days."})
        attrs["working_days"] = sorted(set(days))
        languages = attrs["languages_known"]
        if not isinstance(languages, list) or any(not isinstance(x, str) for x in languages):
            raise serializers.ValidationError({"languages_known": "Enter comma-separated languages."})
        attrs["languages_known"] = list({x.strip().casefold(): x.strip() for x in languages if x.strip()}.values())
        if not attrs["languages_known"]:
            raise serializers.ValidationError({"languages_known": "Enter at least one language."})
        return attrs


class ApplicationOptionsView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        org = request.organization
        return Response({
            "clinics": list(Clinic.objects.filter(organization=org, is_active=True).values("id", "slug")),
            "therapies": list(TherapyOption.objects.filter(organization=org, is_active=True).values("id", "name")),
            "service_areas": list(ServiceArea.objects.filter(organization=org, is_active=True).values("id", "name")),
        })


class ApplicantMobileAvailabilityView(StaffMobileAvailabilityView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (CustomerRegistrationRateThrottle,)


class CompleteApplicationView(APIView):
    parser_classes = (MultiPartParser, FormParser)
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_classes = (CustomerRegistrationRateThrottle,)

    @transaction.atomic
    def post(self, request):
        serializer = CompleteApplicationSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if User.objects.filter(mobile_number=data["mobile"]).exists():
            raise serializers.ValidationError({"mobile": "This mobile number is already registered. Please sign in."})
        try:
            proof = resolve_booking_verification(organization=request.organization, mobile_number=data["mobile"][-10:],
                                                 token=data["mobile_verification_token"], lock=True)
        except Exception as error:
            raise serializers.ValidationError({"mobile": "Mobile verification has expired. Please verify this number again."}) from error
        names = data["full_name"].strip().split(maxsplit=1)
        user = User(username=data["email"], email=data["email"], mobile_number=data["mobile"],
                    first_name=names[0], last_name=names[1] if len(names) > 1 else "")
        user.set_password(data["password"])
        try:
            user.full_clean()
            user.save()
        except (ModelValidationError, IntegrityError) as error:
            raise serializers.ValidationError("This mobile number or email is already registered. Please sign in.") from error
        OrganizationMembership.objects.create(user=user, organization=request.organization)
        category = data.get("practitioner_type", "PHYSIOTHERAPIST")
        qualification = data["qualification"]
        app = PractitionerApplication.objects.create(
            applicant=user, organization=request.organization, clinic=data["clinic"], category=category,
            full_legal_name=data["full_name"], email=data["email"], mobile_number=data["mobile"],
            date_of_birth=data["date_of_birth"], gender=data["gender"], qualification_title=qualification,
            highest_qualification=("WELLNESS_CERTIFICATION" if category == "WELLNESS" else
                                   qualification if qualification in ("BPT", "MPT", "DPT") else "OTHER_PHYSIOTHERAPY"),
            specialization=data.get("specialization", ""), bio=data.get("bio", ""),
            languages=data["languages_known"], experience_years=data["experience_years"],
            experience_months=data.get("experience_months", 0), profile_photo=data["profile_photo"],
            working_days=data["working_days"], working_hours_start=data["working_hours_start"],
            working_hours_end=data["working_hours_end"],
        )
        app.service_areas.set(data["service_areas"])
        for therapy in data["therapy_competencies"]:
            PractitionerCompetency.objects.create(application=app, therapy=therapy)
        for field, kind in (("government_id_document", "GOVERNMENT_ID"), ("qualification_document", "QUALIFICATION"),
                            ("experience_document", "EXPERIENCE"), ("other_document", "ADDITIONAL")):
            if data.get(field):
                DocumentUploadSerializer(context={"application": app}).create({"file": data[field], "kind": kind})
        submit_application(app, actor=user)
        proof.consumed_at = timezone.now()
        proof.save(update_fields=["consumed_at"])
        return Response({"id": str(app.pk), "status": "SUBMITTED", "status_label": "Pending Approval",
                         "detail": "Application submitted successfully."}, status=201)
