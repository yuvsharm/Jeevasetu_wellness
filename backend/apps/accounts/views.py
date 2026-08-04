from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
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

from apps.accounts.audit import record_auth_event
from apps.accounts.models import AuthenticationAuditEvent, User
from apps.accounts.permissions import IsEnabledAuthenticated
from apps.accounts.serializers import (
    DetailResponseSerializer,
    LoginSerializer,
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
        return Response(serializer.validated_data)


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
