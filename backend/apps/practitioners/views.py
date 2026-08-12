import mimetypes
from pathlib import Path

from django.db.models import Q
from django.http import FileResponse
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsEnabledAuthenticated, IsOwnerOrManager
from apps.accounts.role_policy import actor_role_scope
from apps.practitioners.models import (
    PractitionerApplication,
    PractitionerCompetency,
    PractitionerDocument,
    PractitionerProfile,
)
from apps.practitioners.serializers import (
    ApplicationSerializer,
    CompetencySerializer,
    DocumentUploadSerializer,
    ManagerApplicationSerializer,
    OpenToWorkSerializer,
    ProfilePhotoUploadSerializer,
    PublicPractitionerSerializer,
    ReviewActionSerializer,
    VerificationSerializer,
)
from apps.practitioners.services import (
    approve_application,
    manager_can_access,
    record_event,
    review_application,
    set_open_to_work,
    submit_application,
)
from apps.tenancy.permissions import IsActiveOrganizationMember


def profile_photo_content_type(name):
    known_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    return (
        known_types.get(Path(name).suffix.lower())
        or mimetypes.guess_type(name)[0]
        or "application/octet-stream"
    )


class ApplicantMixin:
    permission_classes = (IsEnabledAuthenticated, IsActiveOrganizationMember)

    def get_queryset(self):
        return PractitionerApplication.objects.filter(
            applicant=self.request.user, organization=self.request.organization
        ).prefetch_related("documents", "competencies__therapy")


class MyApplicationListCreateView(ApplicantMixin, generics.ListCreateAPIView):
    serializer_class = ApplicationSerializer


class MyApplicationDetailView(ApplicantMixin, generics.RetrieveUpdateAPIView):
    serializer_class = ApplicationSerializer


class SubmitApplicationView(ApplicantMixin, generics.GenericAPIView):
    serializer_class = ApplicationSerializer

    def post(self, request, pk):
        application = self.get_queryset().filter(pk=pk).first()
        if application is None:
            raise NotFound("Application is unavailable.")
        application = submit_application(application, actor=request.user)
        return Response(ApplicationSerializer(application, context={"request": request}).data)


class WithdrawApplicationView(ApplicantMixin, generics.GenericAPIView):
    serializer_class = ApplicationSerializer

    def post(self, request, pk):
        application = self.get_queryset().filter(pk=pk).first()
        if application is None:
            raise NotFound("Application is unavailable.")
        if application.status not in ("DRAFT", "SUBMITTED", "CORRECTION_REQUIRED"):
            raise ValidationError("This application cannot be withdrawn.")
        application.status = PractitionerApplication.Status.WITHDRAWN
        application.save(update_fields=("status", "updated_at"))
        record_event(application, actor=request.user, action="WITHDRAWN")
        return Response(status=status.HTTP_204_NO_CONTENT)


class CompetencyListCreateView(ApplicantMixin, generics.ListCreateAPIView):
    serializer_class = CompetencySerializer

    def application(self):
        value = (
            self.get_queryset()
            .filter(pk=self.kwargs["pk"], status__in=("DRAFT", "CORRECTION_REQUIRED"))
            .first()
        )
        if value is None:
            raise NotFound("Editable application is unavailable.")
        return value

    def get_queryset(self):
        if not hasattr(self, "request"):
            return PractitionerCompetency.objects.none()
        return PractitionerCompetency.objects.filter(
            application__applicant=self.request.user,
            application__organization=self.request.organization,
            application_id=self.kwargs["pk"],
        )

    def perform_create(self, serializer):
        serializer.save(application=self.application())


class DocumentUploadView(ApplicantMixin, generics.CreateAPIView):
    serializer_class = DocumentUploadSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        application = PractitionerApplication.objects.filter(
            pk=self.kwargs["pk"],
            applicant=self.request.user,
            organization=self.request.organization,
            status__in=("DRAFT", "CORRECTION_REQUIRED"),
        ).first()
        if application is None:
            raise NotFound("Editable application is unavailable.")
        context["application"] = application
        return context


class ProfilePhotoUploadView(ApplicantMixin, generics.GenericAPIView):
    serializer_class = ProfilePhotoUploadSerializer
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request, pk):
        application = PractitionerApplication.objects.filter(
            pk=pk,
            applicant=request.user,
            organization=request.organization,
            status__in=("DRAFT", "CORRECTION_REQUIRED"),
        ).first()
        if application is None:
            raise NotFound("Editable application is unavailable.")
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        application.profile_photo = serializer.validated_data["profile_photo"]
        application.save(update_fields=("profile_photo", "updated_at"))
        return Response({"detail": "Profile photograph uploaded."})

    def get(self, request, pk):
        application = PractitionerApplication.objects.filter(
            pk=pk, applicant=request.user, organization=request.organization
        ).first()
        if application is None or not application.profile_photo:
            raise NotFound("Profile photograph is unavailable.")
        application.profile_photo.open("rb")
        return FileResponse(
            application.profile_photo,
            content_type=profile_photo_content_type(application.profile_photo.name),
        )

    def delete(self, request, pk):
        application = PractitionerApplication.objects.filter(
            pk=pk,
            applicant=request.user,
            organization=request.organization,
            status__in=("DRAFT", "CORRECTION_REQUIRED"),
        ).first()
        if application is None:
            raise NotFound("Editable application is unavailable.")
        if application.profile_photo:
            application.profile_photo.delete(save=False)
            application.profile_photo = ""
            application.save(update_fields=("profile_photo", "updated_at"))
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApplicantDocumentDetailView(ApplicantMixin, generics.GenericAPIView):
    serializer_class = DocumentUploadSerializer

    def get(self, request, pk, document_pk):
        document = PractitionerDocument.objects.filter(
            pk=document_pk,
            application_id=pk,
            application__applicant=request.user,
            application__organization=request.organization,
        ).first()
        if document is None:
            raise NotFound("Document is unavailable.")
        document.file.open("rb")
        return FileResponse(
            document.file,
            as_attachment=False,
            filename=document.original_name,
            content_type=document.content_type,
        )

    def delete(self, request, pk, document_pk):
        document = PractitionerDocument.objects.filter(
            pk=document_pk,
            application_id=pk,
            application__applicant=request.user,
            application__organization=request.organization,
            application__status__in=("DRAFT", "CORRECTION_REQUIRED"),
        ).first()
        if document is None:
            raise NotFound("Document is unavailable.")
        document.file.delete(save=False)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ManagerApplicationListView(generics.ListAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = ManagerApplicationSerializer

    def get_queryset(self):
        queryset = (
            PractitionerApplication.objects.filter(organization=self.request.organization)
            .select_related("applicant", "clinic")
            .prefetch_related("documents", "competencies__therapy")
        )
        level, clinic_ids = actor_role_scope(self.request.user, self.request.organization)
        if level == Role.MANAGER and clinic_ids is not None:
            queryset = queryset.filter(clinic_id__in=clinic_ids)
        status_value = self.request.query_params.get("status")
        search = self.request.query_params.get("search", "").strip()
        if status_value:
            queryset = queryset.filter(status=status_value)
        else:
            queryset = queryset.filter(
                status__in=(
                    PractitionerApplication.Status.SUBMITTED,
                    PractitionerApplication.Status.RESUBMITTED,
                    PractitionerApplication.Status.UNDER_REVIEW,
                    PractitionerApplication.Status.CORRECTION_REQUIRED,
                )
            )
        if search:
            queryset = queryset.filter(
                Q(full_legal_name__icontains=search)
                | Q(email__icontains=search)
                | Q(mobile_number__icontains=search)
            )
        return queryset


class ManagerApplicationDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = ManagerApplicationSerializer

    def get_queryset(self):
        return ManagerApplicationListView.get_queryset(self)


class ReviewApplicationView(generics.GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = ReviewActionSerializer

    def post(self, request, pk):
        application = PractitionerApplication.objects.filter(
            pk=pk, organization=request.organization
        ).first()
        if application is None or not manager_can_access(request.user, application):
            raise NotFound("Application is unavailable.")
        serializer = ReviewActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data["action"] == "approve":
            application = approve_application(application, actor=request.user)
        else:
            application = review_application(
                application, actor=request.user, **serializer.validated_data
            )
        return Response(
            ManagerApplicationSerializer(application, context={"request": request}).data
        )


class VerifyDocumentView(generics.GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = VerificationSerializer

    def post(self, request, pk):
        document = (
            PractitionerDocument.objects.select_related("application")
            .filter(pk=pk, application__organization=request.organization)
            .first()
        )
        if document is None or not manager_can_access(request.user, document.application):
            raise NotFound("Document is unavailable.")
        if document.application.status not in (
            PractitionerApplication.Status.SUBMITTED,
            PractitionerApplication.Status.RESUBMITTED,
            PractitionerApplication.Status.UNDER_REVIEW,
        ):
            raise ValidationError("This document is not in an actionable review state.")
        serializer = VerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document.verification_status = (
            "VERIFIED" if serializer.validated_data["verified"] else "REJECTED"
        )
        document.verified_by = request.user
        document.verified_at = timezone.now()
        document.save(update_fields=("verification_status", "verified_by", "verified_at"))
        record_event(
            document.application,
            actor=request.user,
            action="DOCUMENT_VERIFIED",
            metadata={"document_kind": document.kind},
        )
        return Response({"verification_status": document.verification_status})


class VerifyCompetencyView(generics.GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsOwnerOrManager)
    serializer_class = VerificationSerializer

    def post(self, request, pk):
        competency = (
            PractitionerCompetency.objects.select_related("application")
            .filter(pk=pk, application__organization=request.organization)
            .first()
        )
        if competency is None or not manager_can_access(request.user, competency.application):
            raise NotFound("Competency is unavailable.")
        serializer = VerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        competency.verification_status = (
            "VERIFIED" if serializer.validated_data["verified"] else "REJECTED"
        )
        competency.verified_by = request.user
        competency.verified_at = timezone.now()
        competency.save(update_fields=("verification_status", "verified_by", "verified_at"))
        record_event(
            competency.application,
            actor=request.user,
            action="COMPETENCY_VERIFIED",
            metadata={"therapy_id": str(competency.therapy_id)},
        )
        return Response({"verification_status": competency.verification_status})


class PrivateDocumentView(generics.GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsActiveOrganizationMember)
    serializer_class = DocumentUploadSerializer

    def get(self, request, pk):
        document = (
            PractitionerDocument.objects.select_related("application")
            .filter(pk=pk, application__organization=request.organization)
            .first()
        )
        if document is None:
            raise NotFound("Document is unavailable.")
        if document.application.applicant_id != request.user.id and not manager_can_access(
            request.user, document.application
        ):
            raise PermissionDenied("Private document access is denied.")
        document.file.open("rb")
        return FileResponse(
            document.file,
            as_attachment=False,
            filename=document.original_name,
            content_type=document.content_type,
        )


    def delete(self, request, pk):
        document = PractitionerDocument.objects.filter(
            pk=pk,
            application__applicant=request.user,
            application__organization=request.organization,
            application__status__in=("DRAFT", "CORRECTION_REQUIRED"),
        ).first()
        if document is None:
            raise NotFound("Document is unavailable.")
        document.file.delete(save=False)
        document.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PrivateApplicationPhotoView(generics.GenericAPIView):
    permission_classes = (IsEnabledAuthenticated, IsActiveOrganizationMember)
    serializer_class = ProfilePhotoUploadSerializer

    def get(self, request, pk):
        application = PractitionerApplication.objects.filter(
            pk=pk, organization=request.organization
        ).first()
        if application is None or not application.profile_photo:
            raise NotFound("Profile photograph is unavailable.")
        if application.applicant_id != request.user.id and not manager_can_access(
            request.user, application
        ):
            raise PermissionDenied("Private photograph access is denied.")
        application.profile_photo.open("rb")
        return FileResponse(
            application.profile_photo,
            as_attachment=False,
            filename="profile-photo",
            content_type=profile_photo_content_type(application.profile_photo.name),
        )


class MyOpenToWorkView(generics.GenericAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    serializer_class = OpenToWorkSerializer

    def post(self, request):
        profile = PractitionerProfile.objects.filter(
            user=request.user, organization=request.organization
        ).first()
        if profile is None:
            raise NotFound("Approved practitioner profile is unavailable.")
        serializer = OpenToWorkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_open_to_work(profile, actor=request.user, enabled=serializer.validated_data["enabled"])
        return Response({"is_open_to_work": profile.is_open_to_work})


class PublicPractitionerListView(generics.ListAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PublicPractitionerSerializer
    pagination_class = None

    def get_queryset(self):
        organization = getattr(self.request, "organization", None)
        if organization is None:
            return PractitionerProfile.objects.none()
        return (
            PractitionerProfile.objects.filter(
                organization=organization,
                is_approved=True,
                is_publicly_visible=True,
                user__is_active=True,
                user__is_enabled=True,
            )
            .select_related("user", "source_application")
            .prefetch_related("source_application__competencies__therapy")
        )


class PublicPractitionerDetailView(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PublicPractitionerSerializer

    def get_queryset(self):
        return PublicPractitionerListView.get_queryset(self)


class PublicPractitionerPhotoView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = PublicPractitionerSerializer

    def get(self, request, pk):
        profile = PublicPractitionerListView.get_queryset(self).filter(pk=pk).first()
        if profile is None or not profile.source_application.profile_photo:
            raise NotFound("Photo is unavailable.")
        profile.source_application.profile_photo.open("rb")
        return FileResponse(
            profile.source_application.profile_photo,
            content_type=profile_photo_content_type(
                profile.source_application.profile_photo.name
            ),
        )
