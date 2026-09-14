from django.conf import settings
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
        from apps.accounts.validators import normalize_login_mobile
        identifier = self.validated_data["identifier"].strip()
        query = Q(email__iexact=normalize_email_address(identifier))
        try:
            query |= Q(mobile_number=normalize_login_mobile(identifier))
        except Exception:
            pass
        return User.objects.filter(query).first()


class CustomerOtpLoginSerializer(serializers.Serializer):
    verification_id = serializers.UUIDField()
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    otp = serializers.RegexField(r"^\d{6}$", required=False, write_only=True)
    access_token = serializers.CharField(required=False, write_only=True, trim_whitespace=False, max_length=4096)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate(self, attrs):
        required = "access_token" if settings.MSG91_ENABLED else "otp"
        if not attrs.get(required):
            raise serializers.ValidationError({required: "This field is required for mobile verification."})
        return attrs


class CustomerAddressSerializer(serializers.Serializer):
    address_line_1 = serializers.CharField(max_length=255)
    address_line_2 = serializers.CharField(max_length=255, required=False, allow_blank=True)
    landmark = serializers.CharField(max_length=160, required=False, allow_blank=True)
    city = serializers.CharField(max_length=120)
    region = serializers.CharField(max_length=120)
    pin_code = serializers.RegexField(r"^[1-9]\d{5}$")
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    location_accuracy_meters = serializers.IntegerField(required=False, allow_null=True, min_value=0)
    location_source = serializers.ChoiceField(choices=("MANUAL", "DEVICE"), required=False)


class CustomerRegistrationSerializer(serializers.Serializer):
    booking_verification_token = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=4096
    )
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    full_name = serializers.CharField(max_length=160)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    age = serializers.IntegerField(required=False, min_value=0, max_value=120)
    gender = serializers.ChoiceField(
        choices=("FEMALE", "MALE", "OTHER", "PREFER_NOT_TO_SAY")
    )
    address = CustomerAddressSerializer()
    guardian_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    guardian_relationship = serializers.CharField(max_length=80, required=False, allow_blank=True)
    guardian_mobile = serializers.RegexField(r"^[6-9]\d{9}$", required=False, allow_blank=True)
    profile_photo = serializers.ImageField(required=False, allow_null=True)

    def validate_profile_photo(self, value):
        if value.content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise serializers.ValidationError("Upload a JPG, PNG, or WebP photograph.")
        if value.size > 2 * 1024 * 1024:
            raise serializers.ValidationError("Profile photographs must not exceed 2 MB.")
        return value

    def validate(self, attrs):
        if not attrs.get("date_of_birth") and attrs.get("age") is None:
            raise serializers.ValidationError({"age": "Age or date of birth is required."})
        age = attrs.get("age")
        date_of_birth = attrs.get("date_of_birth")
        if date_of_birth:
            from datetime import date

            today = date.today()
            if date_of_birth > today:
                raise serializers.ValidationError(
                    {"date_of_birth": "Date of birth cannot be in the future."}
                )
            age = today.year - date_of_birth.year - (
                (today.month, today.day) < (date_of_birth.month, date_of_birth.day)
            )
        if age is not None and age < 18 and not all(
            attrs.get(field)
            for field in ("guardian_name", "guardian_relationship", "guardian_mobile")
        ):
            raise serializers.ValidationError(
                {"guardian_name": "Parent or legal guardian details are required for minors."}
            )
        attrs["full_name"] = " ".join(attrs["full_name"].split())
        if len(attrs["full_name"]) < 2:
            raise serializers.ValidationError({"full_name": "Enter the customer's full name."})
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        names = attrs["full_name"].split(" ", 1)
        candidate = User(
            first_name=names[0], last_name=names[1] if len(names) > 1 else "",
            email=normalize_email_address(attrs.get("email", "")),
            mobile_number=f"+91{attrs['mobile_number']}",
        )
        password_validation.validate_password(attrs["password"], candidate)
        attrs["email"] = candidate.email
        return attrs


class PractitionerRegistrationSerializer(serializers.Serializer):
    date_of_birth = serializers.DateField(required=False)

    def validate_date_of_birth(self, value):
        from apps.practitioners.dob import validate_dob, identity_today
        return validate_dob(value, identity_today(organization=self.context.get("organization")))

    booking_verification_token = serializers.CharField(
        write_only=True, trim_whitespace=False, max_length=4096
    )
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    full_name = serializers.CharField(max_length=160)
    email = serializers.EmailField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        names = attrs["full_name"].strip().split(maxsplit=1)
        candidate = User(
            first_name=names[0],
            last_name=names[1] if len(names) > 1 else "",
            email=normalize_email_address(attrs.get("email", "")),
            mobile_number=f"+91{attrs['mobile_number']}",
        )
        password_validation.validate_password(attrs["password"], candidate)
        attrs["email"] = candidate.email
        return attrs

class CustomerPasswordLoginSerializer(serializers.Serializer):
    mobile_number = serializers.RegexField(r"^[6-9]\d{9}$")
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class CustomerPasswordResetSerializer(serializers.Serializer):
    booking_verification_token = serializers.CharField(required=False, write_only=True, trim_whitespace=False, max_length=4096)
    verification_id = serializers.UUIDField()
    mobile_number = serializers.CharField()

    def validate_mobile_number(self, value):
        from apps.accounts.validators import normalize_indian_mobile
        try:
            return normalize_indian_mobile(value)[3:]
        except Exception as error:
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.") from error
    otp = serializers.RegexField(r"^\d{6}$", required=False, write_only=True)
    access_token = serializers.CharField(required=False, write_only=True, trim_whitespace=False, max_length=4096)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)
    confirm_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate(self, attrs):
        required = "access_token" if settings.MSG91_ENABLED else "otp"
        if not attrs.get(required) and not attrs.get("booking_verification_token"):
            raise serializers.ValidationError({required: "This field is required for mobile verification."})
        if attrs["new_password"] != attrs.pop("confirm_password"):
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        return attrs


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(trim_whitespace=False)


class TokenPairResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    user = UserSummarySerializer(read_only=True)
    refresh_max_age = serializers.IntegerField(read_only=True, required=False)


class RefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(read_only=True)
    refresh = serializers.CharField(read_only=True)
    refresh_max_age = serializers.IntegerField(read_only=True, required=False)


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
        if ("mobile_number" in attrs and attrs["mobile_number"] != self.instance.mobile_number
                and self.instance.role_assignments.filter(role="PHYSIOTHERAPIST", is_active=True).exists()):
            raise serializers.ValidationError({"mobile_number": "Use Change Mobile with OTP verification."})
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
