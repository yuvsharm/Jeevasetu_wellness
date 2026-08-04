from django.contrib.auth import password_validation
from django.db.models import Q
from rest_framework import serializers

from apps.accounts.models import RoleAssignment, User
from apps.accounts.validators import normalize_email_address, normalize_mobile_number


class UserSummarySerializer(serializers.ModelSerializer):
    roles = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            "id",
            "first_name",
            "last_name",
            "email",
            "mobile_number",
            "profile_image",
            "roles",
        )
        read_only_fields = fields

    def get_roles(self, user) -> list[str]:
        return list(
            user.role_assignments.filter(is_active=True)
            .order_by("role")
            .values_list("role", flat=True)
        )


class IdentityValidationMixin:
    def validate_email(self, value):
        normalized = normalize_email_address(value)
        queryset = User.objects.filter(email__iexact=normalized)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return normalized

    def validate_mobile_number(self, value):
        try:
            normalized = normalize_mobile_number(value)
        except Exception as error:
            raise serializers.ValidationError(str(error)) from error
        queryset = User.objects.filter(mobile_number=normalized)
        if self.instance is not None:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError("A user with this mobile number already exists.")
        return normalized


class RegistrationSerializer(IdentityValidationMixin, serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "mobile_number",
            "email",
            "password",
            "confirm_password",
        )

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("mobile_number"):
            raise serializers.ValidationError("Email or mobile number is required.")
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        candidate = User(
            first_name=attrs.get("first_name", ""),
            last_name=attrs.get("last_name", ""),
            email=attrs.get("email", ""),
            mobile_number=attrs.get("mobile_number"),
        )
        password_validation.validate_password(attrs["password"], candidate)
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(username=None, **validated_data)


class LoginSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def find_user(self):
        identifier = self.validated_data["identifier"].strip()
        query = Q(email__iexact=normalize_email_address(identifier))
        try:
            query |= Q(mobile_number=normalize_mobile_number(identifier))
        except Exception:
            pass
        return User.objects.filter(query).first()


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(trim_whitespace=False)


class TokenPairResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSummarySerializer(read_only=True)


class RefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)


class DetailResponseSerializer(serializers.Serializer):
    detail = serializers.CharField(read_only=True)


class LogoutSerializer(RefreshSerializer):
    pass


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        user = self.context["request"].user
        if not user.check_password(attrs["old_password"]):
            raise serializers.ValidationError({"old_password": "Old password is incorrect."})
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        password_validation.validate_password(attrs["new_password"], user)
        return attrs


class PasswordResetRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.UUIDField()
    token = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["new_password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        password_validation.validate_password(attrs["new_password"])
        return attrs


class ProfileUpdateSerializer(IdentityValidationMixin, serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "mobile_number", "profile_image")

    def validate(self, attrs):
        email = attrs.get("email", self.instance.email)
        mobile = attrs.get("mobile_number", self.instance.mobile_number)
        if not email and not mobile:
            raise serializers.ValidationError("Email or mobile number is required.")
        return attrs


class RoleAssignmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleAssignment
        fields = ("id", "role", "organization", "clinic", "is_active")
        read_only_fields = fields
