from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from datetime import timedelta
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.accounts.audit import record_auth_event
from apps.accounts.models import AuthenticationAuditEvent, Role, RoleAssignment, User
from apps.accounts.permissions import IsEnabledAuthenticated
from apps.accounts.serializers import (
    DetailResponseSerializer,
    LoginSerializer,
    CustomerOtpLoginSerializer,
    CustomerRegistrationSerializer,
    CustomerPasswordLoginSerializer,
    CustomerPasswordResetSerializer,
    LogoutSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    ProfileUpdateSerializer,
    RefreshResponseSerializer,
    RefreshSerializer,
    RegistrationSerializer,
    TokenPairResponseSerializer,
    UserSummarySerializer,
)
from apps.accounts.services import (
    blacklist_user_refresh_tokens,
    consume_password_reset,
    issue_password_reset,
)
from apps.accounts.validators import normalize_email_address, normalize_mobile_number
from apps.tenancy.models import OrganizationMembership
from apps.appointments.booking_verification import resolve_booking_verification, verify_booking_otp
from apps.patients.models import PatientAddress, PatientProfile


CUSTOMER_SESSION_LIFETIME = timedelta(days=7)


def issue_customer_session(user):
    refresh = RefreshToken.for_user(user)
    refresh["customer_session"] = True
    refresh.set_exp(lifetime=CUSTOMER_SESSION_LIFETIME)
    OutstandingToken.objects.filter(jti=refresh["jti"]).update(
        expires_at=timezone.now() + CUSTOMER_SESSION_LIFETIME
    )
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
        "refresh_max_age": int(CUSTOMER_SESSION_LIFETIME.total_seconds()),
        "user": UserSummarySerializer(user).data,
    }


def eligible_user(identifier):
    query = Q(email__iexact=normalize_email_address(identifier))
    try:
        query |= Q(mobile_number=normalize_mobile_number(identifier))
    except Exception:
        pass
    return User.objects.filter(query, is_active=True, is_enabled=True).first()


class RegistrationView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_register"

    @extend_schema(request=RegistrationSerializer, responses={201: UserSummarySerializer})
    @transaction.atomic
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = serializer.save()
        except IntegrityError as error:
            raise ValidationError("Email or mobile number is already registered.") from error
        if getattr(request, "organization", None) is not None:
            OrganizationMembership.objects.get_or_create(
                user=user, organization=request.organization
            )
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.REGISTRATION,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
        )
        return Response(UserSummarySerializer(user).data, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_login"

    @extend_schema(request=LoginSerializer, responses={200: TokenPairResponseSerializer})
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        user = serializer.find_user()
        if (
            user is None
            or not user.check_password(serializer.validated_data["password"])
            or not user.is_active
            or not user.is_enabled
        ):
            record_auth_event(
                request,
                AuthenticationAuditEvent.Event.LOGIN,
                AuthenticationAuditEvent.Outcome.FAILURE,
                user=user,
                identifier=identifier,
            )
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)

        refresh = RefreshToken.for_user(user)
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.LOGIN,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
        )
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": UserSummarySerializer(user).data,
            }
        )


class CustomerOtpLoginView(APIView):
    """Verify through the booking OTP provider and issue the normal JWT session."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_login"

    @transaction.atomic
    def post(self, request):
        if getattr(request, "organization", None) is None:
            return Response({"detail": "Organization context is unavailable."}, status=404)
        serializer = CustomerOtpLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            token = verify_booking_otp(
                organization=request.organization,
                verification_id=data["verification_id"],
                mobile_number=data["mobile_number"],
                otp=data.get("otp"),
                access_token=data.get("access_token"),
            )
            verification = resolve_booking_verification(
                organization=request.organization,
                mobile_number=data["mobile_number"],
                token=token,
                lock=True,
            )
        except Exception as error:
            raise ValidationError(getattr(error, "messages", [str(error)])) from error
        mobile = f"+91{data['mobile_number']}"
        user = User.objects.select_for_update().filter(mobile_number=mobile).first()
        if user is None:
            raise ValidationError("Register as a customer before signing in.")
        if not user.is_active or not user.is_enabled:
            raise ValidationError("This customer account is unavailable.")
        if user.role_assignments.filter(is_active=True).exclude(role=Role.CUSTOMER).exists():
            raise ValidationError("Staff accounts must use the staff sign-in flow.")
        membership, _ = OrganizationMembership.objects.get_or_create(
            user=user, organization=request.organization
        )
        if not membership.is_active:
            raise ValidationError("This customer account is unavailable.")
        RoleAssignment.objects.get_or_create(
            user=user,
            role=Role.CUSTOMER,
            organization=request.organization,
            clinic=None,
            is_active=True,
            defaults={"organization_membership": membership},
        )
        verification.consumed_at = timezone.now()
        verification.save(update_fields=("consumed_at",))
        refresh = RefreshToken.for_user(user)
        record_auth_event(
            request, AuthenticationAuditEvent.Event.LOGIN,
            AuthenticationAuditEvent.Outcome.SUCCESS, user=user,
        )
        return Response({
            "access": str(refresh.access_token), "refresh": str(refresh),
            "user": UserSummarySerializer(user).data,
        })


class CustomerPasswordLoginView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_login"

    def post(self, request):
        if getattr(request, "organization", None) is None:
            return Response({"detail": "Organization context is unavailable."}, status=404)
        serializer = CustomerPasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        user = User.objects.filter(mobile_number=f"+91{data['mobile_number']}").first()
        valid_customer = bool(
            user
            and user.is_active
            and user.is_enabled
            and user.check_password(data["password"])
            and OrganizationMembership.objects.filter(
                user=user, organization=request.organization, is_active=True
            ).exists()
            and user.role_assignments.filter(
                organization=request.organization, role=Role.CUSTOMER, is_active=True
            ).exists()
            and not user.role_assignments.filter(is_active=True).exclude(role=Role.CUSTOMER).exists()
        )
        if not valid_customer:
            record_auth_event(
                request, AuthenticationAuditEvent.Event.LOGIN,
                AuthenticationAuditEvent.Outcome.FAILURE, user=user,
                identifier=data["mobile_number"],
            )
            return Response({"detail": "Invalid mobile number or password."}, status=401)
        record_auth_event(
            request, AuthenticationAuditEvent.Event.LOGIN,
            AuthenticationAuditEvent.Outcome.SUCCESS, user=user,
        )
        return Response(issue_customer_session(user))


class CustomerRegistrationView(APIView):
    """Create the customer identity and self patient only after mobile ownership verification."""

    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_register"

    @transaction.atomic
    def post(self, request):
        if getattr(request, "organization", None) is None:
            return Response({"detail": "Organization context is unavailable."}, status=404)
        serializer = CustomerRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            verification = resolve_booking_verification(
                organization=request.organization,
                mobile_number=data["mobile_number"],
                token=data["booking_verification_token"],
                lock=True,
            )
        except Exception as error:
            raise ValidationError(getattr(error, "messages", [str(error)])) from error

        mobile = f"+91{data['mobile_number']}"
        existing = User.objects.select_for_update().filter(mobile_number=mobile).first()
        if existing is not None:
            if existing.role_assignments.filter(is_active=True).exclude(role=Role.CUSTOMER).exists():
                raise ValidationError("Staff accounts must use the staff sign-in flow.")
            raise ValidationError("This mobile number is already registered. Please sign in.")
        clinic = request.organization.clinics.filter(is_active=True).order_by("created_at").first()
        if clinic is None:
            raise ValidationError("Customer registration is temporarily unavailable.")

        names = data["full_name"].split(" ", 1)
        user = User.objects.create_user(
            username=None,
            mobile_number=mobile,
            first_name=names[0],
            last_name=names[1] if len(names) > 1 else "",
            email=data.get("email", ""),
            password=data["password"],
        )
        membership = OrganizationMembership.objects.create(
            user=user, organization=request.organization
        )
        RoleAssignment.objects.create(
            user=user,
            role=Role.CUSTOMER,
            organization=request.organization,
            organization_membership=membership,
        )
        patient = PatientProfile(
            organization=request.organization,
            user=user,
            clinic=clinic,
            full_name=data["full_name"],
            mobile_number=data["mobile_number"],
            gender=data["gender"],
            date_of_birth=data.get("date_of_birth"),
            age=data.get("age"),
            emergency_contact_name=data["full_name"],
            emergency_contact_relationship="Self",
            emergency_contact_mobile=data["mobile_number"],
            guardian_name=data.get("guardian_name", ""),
            guardian_relationship=data.get("guardian_relationship", ""),
            guardian_mobile=data.get("guardian_mobile", ""),
        )
        patient.save()
        address = PatientAddress(
            patient=patient,
            label="Home",
            is_primary=True,
            **data["address"],
        )
        address.full_clean()
        address.save()
        verification.consumed_at = timezone.now()
        verification.save(update_fields=("consumed_at",))
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.REGISTRATION,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
        )
        return Response(issue_customer_session(user), status=status.HTTP_201_CREATED)


class CustomerPasswordResetView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_password_reset"

    @transaction.atomic
    def post(self, request):
        if getattr(request, "organization", None) is None:
            return Response({"detail": "Organization context is unavailable."}, status=404)
        serializer = CustomerPasswordResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            token = verify_booking_otp(
                organization=request.organization,
                verification_id=data["verification_id"], mobile_number=data["mobile_number"],
                otp=data.get("otp"), access_token=data.get("access_token"),
            )
            verification = resolve_booking_verification(
                organization=request.organization, mobile_number=data["mobile_number"],
                token=token, lock=True,
            )
        except Exception as error:
            raise ValidationError(getattr(error, "messages", [str(error)])) from error
        user = User.objects.select_for_update().filter(mobile_number=f"+91{data['mobile_number']}").first()
        eligible = bool(
            user and user.is_active and user.is_enabled
            and OrganizationMembership.objects.filter(user=user, organization=request.organization, is_active=True).exists()
            and user.role_assignments.filter(organization=request.organization, role=Role.CUSTOMER, is_active=True).exists()
            and not user.role_assignments.filter(is_active=True).exclude(role=Role.CUSTOMER).exists()
        )
        if not eligible:
            raise ValidationError("Password reset could not be completed.")
        from django.contrib.auth import password_validation

        password_validation.validate_password(data["new_password"], user)
        user.set_password(data["new_password"])
        user.save(update_fields=("password",))
        verification.consumed_at = timezone.now()
        verification.save(update_fields=("consumed_at",))
        blacklist_user_refresh_tokens(user)
        record_auth_event(
            request, AuthenticationAuditEvent.Event.PASSWORD_RESET_COMPLETE,
            AuthenticationAuditEvent.Outcome.SUCCESS, user=user,
        )
        return Response({"detail": "Password reset completed. Sign in with your new password."})


class RefreshView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_refresh"

    @extend_schema(request=RefreshSerializer, responses={200: RefreshResponseSerializer})
    def post(self, request):
        request_serializer = RefreshSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)
        raw_refresh = request_serializer.validated_data["refresh"]
        user = None
        try:
            submitted = RefreshToken(raw_refresh)
            user = User.objects.filter(pk=submitted["user_id"]).first()
            if user is None or not user.is_active or not user.is_enabled:
                raise TokenError("Token user is unavailable")
            if submitted.get("customer_session"):
                if not user.role_assignments.filter(role=Role.CUSTOMER, is_active=True).exists():
                    raise TokenError("Token user is unavailable")
                validated_data = {
                    "access": str(submitted.access_token),
                    "refresh": raw_refresh,
                    "refresh_max_age": max(0, int(submitted["exp"] - timezone.now().timestamp())),
                }
                serializer = None
            else:
                serializer = TokenRefreshSerializer(data={"refresh": raw_refresh})
                serializer.is_valid(raise_exception=True)
        except (TokenError, KeyError, APIException):
            record_auth_event(
                request,
                AuthenticationAuditEvent.Event.REFRESH,
                AuthenticationAuditEvent.Outcome.FAILURE,
                user=user,
            )
            return Response(
                {"detail": "Refresh token is invalid or expired."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.REFRESH,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
        )
        return Response(validated_data if serializer is None else serializer.validated_data)


class LogoutView(APIView):
    permission_classes = (IsEnabledAuthenticated,)
    throttle_scope = "auth_logout"

    @extend_schema(request=LogoutSerializer, responses={204: None})
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            if str(refresh["user_id"]) != str(request.user.id):
                raise TokenError("Token owner mismatch")
            refresh.blacklist()
        except (TokenError, KeyError):
            record_auth_event(
                request,
                AuthenticationAuditEvent.Event.LOGOUT,
                AuthenticationAuditEvent.Outcome.FAILURE,
                user=request.user,
            )
            raise ValidationError("Refresh token is invalid or expired.") from None
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.LOGOUT,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=request.user,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordChangeView(APIView):
    permission_classes = (IsEnabledAuthenticated,)
    throttle_scope = "auth_password_change"

    @extend_schema(request=PasswordChangeSerializer, responses={200: DetailResponseSerializer})
    def post(self, request):
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=("password",))
        blacklist_user_refresh_tokens(request.user)
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.PASSWORD_CHANGE,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=request.user,
        )
        return Response({"detail": "Password changed. Sign in again with the new password."})


class PasswordResetRequestView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_password_reset"

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={202: DetailResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        identifier = serializer.validated_data["identifier"]
        user = eligible_user(identifier)
        response = {"detail": "If an eligible account exists, reset instructions are available."}
        if user is not None:
            reset, token = issue_password_reset(user)
            if settings.AUTH_EXPOSE_PASSWORD_RESET_TOKEN:
                response.update(
                    {"uid": str(user.id), "token": token, "expires_at": reset.expires_at}
                )
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.PASSWORD_RESET_REQUEST,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
            identifier=identifier,
        )
        return Response(response, status=status.HTTP_202_ACCEPTED)


class PasswordResetConfirmView(APIView):
    authentication_classes = ()
    permission_classes = (AllowAny,)
    throttle_scope = "auth_password_reset"

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={200: DetailResponseSerializer},
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = consume_password_reset(
            serializer.validated_data["uid"],
            serializer.validated_data["token"],
            serializer.validated_data["new_password"],
        )
        if user is None:
            record_auth_event(
                request,
                AuthenticationAuditEvent.Event.PASSWORD_RESET_COMPLETE,
                AuthenticationAuditEvent.Outcome.FAILURE,
            )
            raise ValidationError("Password reset token is invalid or expired.")
        record_auth_event(
            request,
            AuthenticationAuditEvent.Event.PASSWORD_RESET_COMPLETE,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
        )
        return Response({"detail": "Password reset completed."})


class ProfileView(RetrieveUpdateAPIView):
    permission_classes = (IsEnabledAuthenticated,)
    throttle_scope = "auth_profile"

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method in {"PUT", "PATCH"}:
            return ProfileUpdateSerializer
        return UserSummarySerializer

    def perform_update(self, serializer):
        user = serializer.save()
        record_auth_event(
            self.request,
            AuthenticationAuditEvent.Event.PROFILE_UPDATE,
            AuthenticationAuditEvent.Outcome.SUCCESS,
            user=user,
        )
