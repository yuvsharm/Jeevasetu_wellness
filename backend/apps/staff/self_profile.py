"""Self-service edits of the existing staff identity; operational claims stay protected."""
from pathlib import Path
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from apps.accounts.models import Role
from apps.accounts.permissions import IsEnabledAuthenticated, IsPhysiotherapist, IsOwnerOrManager
from apps.accounts.role_policy import actor_role_scope
from apps.staff.models import StaffProfile
from apps.staff.serializers import StaffProfileSerializer
from apps.practitioners.models import PractitionerCompetency, PractitionerDocument, PractitionerAuditEvent
from apps.practitioners.serializers import DocumentUploadSerializer, ProfilePhotoUploadSerializer
from apps.practitioners.services import upload_checksum

class SelfProfileSerializer(StaffProfileSerializer):
    first_name = serializers.CharField(source="user.first_name", max_length=150)
    last_name = serializers.CharField(source="user.last_name", max_length=150, allow_blank=True)
    service_area_names = serializers.SlugRelatedField(source="service_areas", many=True, read_only=True, slug_field="name")
    class Meta(StaffProfileSerializer.Meta):
        fields = StaffProfileSerializer.Meta.fields + ("first_name", "last_name", "service_area_names")
    def validate(self, attrs):
        allowed = {"first_name", "last_name", "email", "gender", "date_of_birth", "experience_years", "experience_months", "languages_known", "specialization_ids", "bio", "service_area_ids", "is_publicly_visible", "current_address", "city", "pin_code", "base_latitude", "base_longitude", "base_location_accuracy_meters", "base_location_source"}
        invalid = set(self.initial_data) - allowed
        if invalid:
            raise serializers.ValidationError({key: "Use the secure verification workflow to change this field." for key in invalid})
        return super().validate(attrs)
    @transaction.atomic
    def update(self, instance, validated_data):
        try:
            return super().update(instance, validated_data)
        except DjangoValidationError as error:
            raise serializers.ValidationError(error.message_dict) from error
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.pop("profile_photo", None)
        if data.get("photo_url"):
            data["photo_url"] = f"/api/staff/me/photo?v={instance.updated_at.timestamp()}"
        data["documents"] = [{"id": str(d.pk), "label": d.label} for d in instance.documents.all()]
        return data

class SelfProfileBase(GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsPhysiotherapist)
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    def profile(self):
        profile = StaffProfile.objects.filter(user=self.request.user, organization=self.request.organization, staff_type=Role.PHYSIOTHERAPIST).first()
        if profile is None:
            raise NotFound("Your professional profile is unavailable.")
        return profile

    def practitioner_profile(self):
        try:
            return self.profile().practitioner_profile
        except ObjectDoesNotExist as error:
            raise NotFound("Your approved professional profile is unavailable.") from error

class SelfPhotoView(SelfProfileBase):
    serializer_class = ProfilePhotoUploadSerializer
    def get(self, request):
        from apps.staff.photos import profile_photo
        from apps.practitioners.views import profile_photo_content_type
        photo = profile_photo(self.profile())
        if not photo:
            raise NotFound("No profile photo uploaded.")
        response = FileResponse(photo.open("rb"), content_type=profile_photo_content_type(photo.name))
        response["Cache-Control"] = "private, no-store"
        return response
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        profile = self.profile()
        profile.profile_photo = serializer.validated_data["profile_photo"]
        profile.profile_photo_removed = False
        profile.save(update_fields=["profile_photo", "profile_photo_removed", "updated_at"])
        return Response({"detail": "Profile photo updated."})
    def delete(self, request):
        profile = self.profile()
        # Keep the stored file and enrollment snapshot; suppress the canonical photo.
        profile.profile_photo_removed = True
        profile.save(update_fields=["profile_photo_removed", "updated_at"])
        return Response({"detail": "Profile photo removed."})

class SelfOptionsView(SelfProfileBase):
    def get(self, request, *args, **kwargs):
        from apps.staff.models import ServiceArea, Specialization
        from apps.appointments.models import TherapyOption
        return Response({"specializations": list(Specialization.objects.filter(is_active=True).values("id", "name")), "service_areas": list(ServiceArea.objects.filter(organization=request.organization, is_active=True).values("id", "name")), "therapies": list(TherapyOption.objects.filter(organization=request.organization, is_active=True).order_by("display_order", "name").values("id", "name"))})


class SelfCompetenciesView(SelfProfileBase):
    def get(self, request, *args, **kwargs):
        from apps.appointments.models import TherapyOption
        staff = self.profile()
        selected = {str(value) for value in staff.therapy_competencies.values_list("id", flat=True)}
        result = []
        for therapy in TherapyOption.objects.filter(organization=request.organization, is_active=True).order_by("display_order", "name"):
            therapy_id = str(therapy.id)
            result.append({"therapy_id": therapy_id, "therapy_name": therapy.name, "status": "SELECTED" if therapy_id in selected else "NOT_SELECTED"})
        return Response(result)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        from apps.appointments.models import TherapyOption
        staff = self.profile()
        profile = self.practitioner_profile()
        therapy = TherapyOption.objects.filter(pk=request.data.get("therapy_id"), organization=request.organization, is_active=True).first()
        if therapy is None:
            raise ValidationError({"therapy_id": "Select an active therapy."})
        if staff.therapy_competencies.filter(pk=therapy.pk).exists():
            return Response({"therapy_id": str(therapy.id), "status": "SELECTED", "detail": "Therapy is already selected."})
        from apps.practitioners.services import add_competency
        add_competency(profile, therapy, actor=request.user)
        return Response({"therapy_id": str(therapy.id), "status": "SELECTED", "detail": "Therapies updated successfully."}, status=201)

    @transaction.atomic
    def delete(self, request, *args, **kwargs):
        from apps.practitioners.services import remove_competency
        profile = self.practitioner_profile()
        staff = self.profile()
        therapy_id = request.data.get("therapy_id")
        therapy = staff.therapy_competencies.filter(pk=therapy_id).first()
        if therapy is None:
            raise ValidationError("This therapy is not currently selected.")
        competency = profile.competency_requests.select_for_update().filter(
            therapy=therapy
        ).select_related("therapy").first()
        if competency is None:
            application = getattr(profile, "source_application", None)
            competency = application and application.competencies.select_for_update().filter(
                therapy=therapy
            ).select_related("therapy").first()
        if competency is None:
            competency = PractitionerCompetency.objects.create(
                profile=profile, therapy=therapy,
                verification_status=PractitionerCompetency.Verification.VERIFIED,
            )
        remove_competency(competency, actor=request.user, profile=profile)
        return Response(status=204)


class ManagedCompetenciesView(SelfCompetenciesView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)

    def profile(self):
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        queryset = StaffProfile.objects.filter(
            pk=self.kwargs["pk"], organization=self.request.organization,
            staff_type=Role.PHYSIOTHERAPIST,
        )
        if level != Role.OWNER:
            queryset = queryset.filter(clinic_id__in=clinic_ids or ())
        profile = queryset.first()
        if profile is None:
            raise NotFound("Therapist profile is unavailable.")
        return profile

class SelfCredentialsView(SelfProfileBase):
    serializer_class = DocumentUploadSerializer
    def get(self, request):
        profile = self.profile().practitioner_profile
        app = getattr(profile, "source_application", None)
        documents = list(app.documents.all()) if app else []
        documents += list(profile.credential_documents.order_by("created_at"))
        latest = {d.kind: d for d in documents}
        return Response([{"id": str(d.pk), "kind": d.kind, "status": d.verification_status, "name": d.original_name} for d in latest.values()])
    @transaction.atomic
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        file = data["file"]
        profile = self.profile().practitioner_profile
        document = PractitionerDocument.objects.create(profile=profile, kind=data["kind"], file=file, original_name=Path(file.name).name, content_type=file.content_type, size_bytes=file.size, checksum_sha256=upload_checksum(file))
        PractitionerAuditEvent.objects.create(profile=profile, organization=profile.organization, actor=request.user, action="SUBMITTED", metadata={"document_kind": document.kind, "status": "PENDING"})
        return Response({"id": str(document.pk), "status": "PENDING", "detail": "Replacement submitted. Verification Pending."}, status=201)

class CredentialReviewView(GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    def scoped(self):
        level, clinics = actor_role_scope(self.request.user, self.request.organization)
        qs = PractitionerDocument.objects.filter(profile__organization=self.request.organization).select_related("profile__user")
        if level != Role.OWNER:
            qs = qs.filter(profile__clinic_id__in=clinics or [])
        return qs
    def get(self, request):
        return Response([{"id": str(d.pk), "name": d.profile.user.get_full_name(), "kind": d.kind, "status": d.verification_status, "url": f"/api/staff/credentials/{d.pk}"} for d in self.scoped().filter(verification_status="PENDING")])
    @transaction.atomic
    def post(self, request, pk):
        document = self.scoped().select_for_update().filter(pk=pk, verification_status="PENDING").first()
        if not document:
            raise NotFound("Pending credential is unavailable.")
        status = request.data.get("status")
        if status not in ("VERIFIED", "REJECTED"):
            raise ValidationError("Choose Verified or Rejected.")
        document.verification_status = status
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.save()
        PractitionerAuditEvent.objects.create(profile=document.profile, organization=request.organization, actor=request.user, action="DOCUMENT_VERIFIED", metadata={"document_kind": document.kind, "status": status})
        return Response({"status": status})

class CredentialFileView(CredentialReviewView):
    def get(self, request, pk):
        document = self.scoped().filter(pk=pk).first()
        if not document:
            raise NotFound("Credential is unavailable.")
        response = FileResponse(document.file.open("rb"), content_type=document.content_type, filename=document.original_name)
        response["Cache-Control"] = "private, no-store"
        return response


class ChangeMobileSerializer(serializers.Serializer):
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    current_password = serializers.CharField(write_only=True, trim_whitespace=False)
    booking_verification_token = serializers.CharField(write_only=True, max_length=4096)

class SelfMobileView(SelfProfileBase):
    serializer_class = ChangeMobileSerializer
    @transaction.atomic
    def post(self, request):
        from apps.accounts.models import User
        from apps.accounts.services import blacklist_user_refresh_tokens
        from apps.appointments.booking_verification import resolve_booking_verification
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.select_for_update().get(pk=request.user.pk)
        if not user.check_password(data["current_password"]):
            raise ValidationError("Current password is incorrect.")
        mobile = "+91" + data["mobile_number"]
        if User.objects.filter(mobile_number=mobile).exclude(pk=user.pk).exists():
            raise ValidationError("This mobile number cannot be used.")
        try:
            proof = resolve_booking_verification(organization=request.organization, mobile_number=data["mobile_number"], token=data["booking_verification_token"], lock=True)
        except DjangoValidationError as error:
            raise ValidationError("Verification expired or invalid. Please verify the new mobile again.") from error
        user.mobile_number = mobile
        user.save(update_fields=["mobile_number"])
        proof.consumed_at = timezone.now()
        proof.save(update_fields=["consumed_at"])
        blacklist_user_refresh_tokens(user)
        return Response({"detail": "Mobile updated. Please sign in again."})
