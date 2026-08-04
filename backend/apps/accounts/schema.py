from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme


class EnabledUserJWTScheme(SimpleJWTScheme):
    target_class = "apps.accounts.authentication.EnabledUserJWTAuthentication"
