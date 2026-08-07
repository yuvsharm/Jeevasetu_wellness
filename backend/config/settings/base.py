from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env()

SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-development-key")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "drf_spectacular",
    "rest_framework_simplejwt.token_blacklist",
    "apps.accounts",
    "apps.tenancy",
    "apps.appointments",
    "apps.availability",
    "apps.staff",
    "apps.patients",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.tenancy.middleware.TenantContextMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
FILE_UPLOAD_PERMISSIONS = 0o640
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o750
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.EnabledUserJWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "UNAUTHENTICATED_USER": None,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "auth_register": "5/hour",
        "auth_login": "10/minute",
        "auth_refresh": "30/minute",
        "auth_logout": "30/minute",
        "auth_password_change": "10/hour",
        "auth_password_reset": "5/hour",
        "auth_profile": "60/minute",
    },
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "USER_AUTHENTICATION_RULE": "apps.accounts.authentication.enabled_user_authentication_rule",
    "CHECK_REVOKE_TOKEN": True,
}
SPECTACULAR_SETTINGS = {
    "TITLE": "Jeevasetu Wellness API",
    "DESCRIPTION": "Backend API for the Jeevasetu Wellness platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "ENUM_NAME_OVERRIDES": {
        "AppointmentRequestStatus": "apps.appointments.models.AppointmentRequest.Status",
        "OperationalAppointmentStatus": "apps.appointments.models.Appointment.Status",
        "AppointmentAssignmentStatus": ("apps.appointments.models.Appointment.AssignmentStatus"),
        "AppointmentChangeRequestKind": ("apps.appointments.models.AppointmentChangeRequest.Kind"),
        "AppointmentChangeRequestStatus": (
            "apps.appointments.models.AppointmentChangeRequest.Status"
        ),
        "AvailabilityExceptionKind": "apps.availability.models.AvailabilityException.Kind",
        "AppointmentCancellationCategory": (
            "apps.appointments.models.Appointment.CancellationCategory"
        ),
    },
}

REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
REDIS_SOCKET_CONNECT_TIMEOUT = env.float("REDIS_SOCKET_CONNECT_TIMEOUT", default=2.0)
REDIS_SOCKET_TIMEOUT = env.float("REDIS_SOCKET_TIMEOUT", default=2.0)
AUTH_RATE_LIMIT_REDIS_URL = env(
    "AUTH_RATE_LIMIT_REDIS_URL", default=f"{REDIS_URL.rsplit('/', 1)[0]}/1"
)
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": AUTH_RATE_LIMIT_REDIS_URL,
        "OPTIONS": {"socket_connect_timeout": REDIS_SOCKET_CONNECT_TIMEOUT},
    }
}

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=None)
CELERY_TASK_IGNORE_RESULT = CELERY_RESULT_BACKEND is None
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_ENABLE_UTC = True
CELERY_TASK_TRACK_STARTED = False
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = env.int("CELERY_WORKER_PREFETCH_MULTIPLIER", default=1)
CELERY_WORKER_MAX_TASKS_PER_CHILD = env.int("CELERY_WORKER_MAX_TASKS_PER_CHILD", default=1000)
CELERY_TASK_SOFT_TIME_LIMIT = env.int("CELERY_TASK_SOFT_TIME_LIMIT", default=270)
CELERY_TASK_TIME_LIMIT = env.int("CELERY_TASK_TIME_LIMIT", default=300)
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": env.int("CELERY_VISIBILITY_TIMEOUT", default=3600),
}
CELERY_IMPORTS = ("config.tasks",)
CELERY_BEAT_SCHEDULE = {}

CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_NAME = "jeevasetu_session"
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True

AUTH_PASSWORD_RESET_TIMEOUT_SECONDS = env.int("AUTH_PASSWORD_RESET_TIMEOUT_SECONDS", default=1800)
AUTH_EXPOSE_PASSWORD_RESET_TOKEN = False

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO")

VISIT_OTP_EXPIRY_MINUTES = env.int("VISIT_OTP_EXPIRY_MINUTES", default=15)
VISIT_OTP_WINDOW_BEFORE_MINUTES = env.int("VISIT_OTP_WINDOW_BEFORE_MINUTES", default=60)
VISIT_OTP_WINDOW_AFTER_MINUTES = env.int("VISIT_OTP_WINDOW_AFTER_MINUTES", default=120)
VISIT_OTP_MAX_ATTEMPTS = env.int("VISIT_OTP_MAX_ATTEMPTS", default=5)
VISIT_OTP_RATE_LIMIT_ATTEMPTS = env.int("VISIT_OTP_RATE_LIMIT_ATTEMPTS", default=10)
VISIT_OTP_RATE_LIMIT_WINDOW_SECONDS = env.int("VISIT_OTP_RATE_LIMIT_WINDOW_SECONDS", default=300)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"redact_sensitive": {"()": "config.logging.SensitiveDataFilter"}},
    "formatters": {"json": {"()": "config.logging.JsonFormatter"}},
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["redact_sensitive"],
            "formatter": "json",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
