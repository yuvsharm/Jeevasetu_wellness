from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed


def enabled_user_authentication_rule(user):
    return user is not None and user.is_active and user.is_enabled


class EnabledUserJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not user.is_enabled:
            raise AuthenticationFailed("User is disabled.", code="user_disabled")
        return user
