"""Organization-scoped, Owner-curated professional reference content."""
import re
from urllib.parse import urlparse, parse_qs
from django.db import transaction
from django.http import FileResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
from rest_framework.response import Response
from apps.accounts.models import Role
from apps.accounts.permissions import IsEnabledAuthenticated
from apps.accounts.role_policy import actor_role_scope
from apps.appointments.models import TherapyOption
from apps.practitioners.models import TherapyLearningGuide, TherapyLearningImage, TherapyLearningVideo
from apps.practitioners.serializers import ProfilePhotoUploadSerializer

SECTIONS = ("overview", "indications", "contraindications", "patient_preparation", "practitioner_preparation", "equipment", "procedure", "positioning", "duration", "precautions", "stop_criteria", "aftercare", "common_mistakes", "documentation", "key_takeaways")

def youtube_id(value):
    url = urlparse(value)
    if url.scheme != "https" or url.username or url.password or ":" in url.netloc:
        raise serializers.ValidationError("Use a valid HTTPS YouTube video URL.")
    if url.hostname in ("youtube.com", "www.youtube.com") and url.path == "/watch":
        ident = parse_qs(url.query).get("v", [""])[0]
    elif url.hostname == "youtu.be":
        ident = url.path.lstrip("/")
    else:
        ident = ""
    if not re.fullmatch(r"[A-Za-z0-9_-]{11}", ident):
        raise serializers.ValidationError("Use a YouTube watch or youtu.be video URL.")
    return ident

class GuideSerializer(serializers.ModelSerializer):
    therapy_name = serializers.CharField(source="therapy.name", read_only=True)
    clinical_approval = serializers.BooleanField(write_only=True, required=False, default=False)
    class Meta:
        model = TherapyLearningGuide
        fields = ("id", "therapy", "therapy_name", "title_en", "title_hi", "content_en", "content_hi", "learning_minutes", "published", "clinical_approval", "version", "reviewed_at", "updated_at")
        read_only_fields = ("id", "version", "reviewed_at", "updated_at")
    def validate_therapy(self, value):
        if value.organization_id != self.context["request"].organization.id or not value.is_active:
            raise serializers.ValidationError("Select an active therapy in your organization.")
        if self.instance and self.instance.therapy_id != value.pk:
            raise serializers.ValidationError("A guide cannot be moved to another therapy.")
        return value
    def validate_content_en(self, value):
        return self.validate_content(value)
    def validate_content_hi(self, value):
        return self.validate_content(value)
    def validate_content(self, value):
        if not isinstance(value, dict) or set(value) - set(SECTIONS):
            raise serializers.ValidationError("Use the supported learning sections.")
        if any(not isinstance(v, str) or len(v) > 12000 for v in value.values()):
            raise serializers.ValidationError("Each section must be text of at most 12,000 characters.")
        return value
    def validate(self, attrs):
        clinical_approval = attrs.pop("clinical_approval", False)
        if attrs.get("published") is True:
            if not clinical_approval:
                raise serializers.ValidationError("Clinical approval is required before publishing.")
            for lang in ("en", "hi"):
                content = attrs.get(f"content_{lang}", getattr(self.instance, f"content_{lang}", {}))
                if any(not content.get(key, "").strip() for key in SECTIONS):
                    raise serializers.ValidationError("Complete and clinically review every English and Hindi section before publishing.")
            if not attrs.get("title_hi", getattr(self.instance, "title_hi", "")):
                raise serializers.ValidationError("Add the approved Hindi title before publishing.")
        return attrs
    def to_representation(self, value):
        result = super().to_representation(value)
        owner = self.context.get("owner", False)
        result["images"] = [{"id": str(i.pk), "url": f"/api/learning/images/{i.pk}", "caption_en": i.caption_en, "caption_hi": i.caption_hi, "alt_text": i.alt_text, "sort_order": i.sort_order} for i in value.images.filter(rights_confirmed=True)]
        result["videos"] = VideoSerializer(value.videos.all() if owner else value.videos.filter(approved=True), many=True).data
        result["sections"] = SECTIONS
        return result

class VideoSerializer(serializers.ModelSerializer):
    video_id = serializers.SerializerMethodField()
    class Meta:
        model = TherapyLearningVideo
        fields = ("id", "title", "youtube_url", "language", "description", "approved", "sort_order", "video_id")
        read_only_fields = ("id", "video_id")
    def validate_youtube_url(self, value):
        youtube_id(value)
        return value
    def get_video_id(self, value):
        return youtube_id(value.youtube_url)

class ImageSerializer(serializers.ModelSerializer):
    image = serializers.ImageField()
    class Meta:
        model = TherapyLearningImage
        fields = ("id", "image", "caption_en", "caption_hi", "alt_text", "sort_order", "rights_confirmed")
        read_only_fields = ("id",)
    def validate_image(self, value):
        return ProfilePhotoUploadSerializer().validate_profile_photo(value)
    def validate(self, attrs):
        if not attrs.get("rights_confirmed", getattr(self.instance, "rights_confirmed", False)):
            raise serializers.ValidationError("Confirm this image is organization-owned or licensed for use.")
        return attrs

class LearningBase(GenericAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    parser_classes = (JSONParser, MultiPartParser, FormParser)
    def owner(self):
        level, _ = actor_role_scope(self.request.user, self.request.organization)
        return level == Role.OWNER
    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not getattr(request, "organization", None):
            raise NotFound("Organization is unavailable.")
        if not self.owner() and not request.user.role_assignments.filter(organization=request.organization, role=Role.PHYSIOTHERAPIST, is_active=True, organization_membership__is_active=True).exists():
            raise PermissionDenied("Learning guides are available to authorized practitioners.")
        if request.method not in ("GET", "HEAD", "OPTIONS") and not self.owner():
            raise PermissionDenied("Only the Owner can manage learning content.")
    def guides(self):
        qs = TherapyLearningGuide.objects.filter(therapy__organization=self.request.organization, therapy__is_active=True).select_related("therapy").prefetch_related("images", "videos")
        return qs if self.owner() else qs.filter(published=True)
    def guide(self, pk):
        value = self.guides().filter(pk=pk).first()
        if value is None:
            raise NotFound("Learning guide is unavailable.")
        return value
    def output(self, value):
        return GuideSerializer(value, context={"request": self.request, "owner": self.owner()}).data

class LearningCollection(LearningBase):
    def get(self, request):
        return Response({"guides": [self.output(g) for g in self.guides().order_by("therapy__name")], "therapies": list(TherapyOption.objects.filter(organization=request.organization, is_active=True).values("id", "name")), "sections": SECTIONS})
    def post(self, request):
        serializer = GuideSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        guide = serializer.save(reviewed_by=request.user if serializer.validated_data.get("published") else None, reviewed_at=timezone.now() if serializer.validated_data.get("published") else None)
        return Response(self.output(guide), status=201)

class LearningDetail(LearningBase):
    def get(self, request, pk):
        return Response(self.output(self.guide(pk)))
    @transaction.atomic
    def patch(self, request, pk):
        guide = self.guides().select_for_update().filter(pk=pk).first()
        if guide is None:
            raise NotFound("Learning guide is unavailable.")
        serializer = GuideSerializer(guide, data=request.data, partial=True, context={"request": request})
        serializer.is_valid(raise_exception=True)
        published = serializer.validated_data.get("published", guide.published)
        guide = serializer.save(version=guide.version+1, reviewed_by=request.user if published else None, reviewed_at=timezone.now() if published else None)
        return Response(self.output(guide))
    def delete(self, request, pk):
        guide = self.guide(pk)
        guide.published = False
        guide.version += 1
        guide.save()
        return Response({"detail": "Guide unpublished. Content retained."})

class LearningAssets(LearningBase):
    @transaction.atomic
    def post(self, request, pk, kind):
        guide = self.guide(pk)
        if kind not in ("images", "videos"):
            raise NotFound("Resource type is unavailable.")
        serializer = ImageSerializer(data=request.data) if kind == "images" else VideoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(guide=guide)
        guide.version += 1
        guide.save()
        return Response(self.output(guide), status=201)

class LearningAssetDetail(LearningBase):
    def asset(self, pk, kind, asset_pk):
        guide = self.guide(pk)
        if kind not in ("images", "videos"):
            raise NotFound("Resource type is unavailable.")
        value = (guide.images if kind == "images" else guide.videos).filter(pk=asset_pk).first()
        if value is None:
            raise NotFound("Resource is unavailable.")
        return guide, value
    def patch(self, request, pk, kind, asset_pk):
        guide, value = self.asset(pk, kind, asset_pk)
        serializer = ImageSerializer(value, data=request.data, partial=True) if kind == "images" else VideoSerializer(value, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        guide.version += 1
        guide.save()
        return Response(self.output(guide))
    def delete(self, request, pk, kind, asset_pk):
        guide, value = self.asset(pk, kind, asset_pk)
        value.delete()
        guide.version += 1
        guide.save()
        return Response(self.output(guide))

class LearningImageFile(LearningBase):
    def get(self, request, pk):
        value = TherapyLearningImage.objects.filter(pk=pk, guide__in=self.guides(), rights_confirmed=True).first()
        if value is None:
            raise NotFound("Image is unavailable.")
        response = FileResponse(value.image.open("rb"))
        response["Cache-Control"] = "private, no-store"
        return response
