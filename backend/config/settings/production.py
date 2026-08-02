from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import env


def require_secure_secret(value):
    if len(value) < 50 or value.startswith(("unsafe-", "replace-", "change-")):
        raise ImproperlyConfigured("DJANGO_SECRET_KEY must be a strong production value")
    return value


def require_hosts(values):
    if not values or "*" in values or any("://" in value for value in values):
        raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain explicit hostnames")
    return values


def require_https_origins(name, values):
    if not values or any(urlparse(value).scheme != "https" for value in values):
        raise ImproperlyConfigured(f"{name} must contain explicit HTTPS origins")
    return values


def require_url_scheme(name, value, schemes):
    if urlparse(value).scheme not in schemes:
        allowed = ", ".join(sorted(schemes))
        raise ImproperlyConfigured(f"{name} must use one of these schemes: {allowed}")
    return value


SECRET_KEY = require_secure_secret(env("DJANGO_SECRET_KEY"))
ALLOWED_HOSTS = require_hosts(env.list("DJANGO_ALLOWED_HOSTS"))
CORS_ALLOWED_ORIGINS = env.list("DJANGO_CORS_ALLOWED_ORIGINS", default=[])
if CORS_ALLOWED_ORIGINS:
    require_https_origins("DJANGO_CORS_ALLOWED_ORIGINS", CORS_ALLOWED_ORIGINS)
CSRF_TRUSTED_ORIGINS = require_https_origins(
    "DJANGO_CSRF_TRUSTED_ORIGINS", env.list("DJANGO_CSRF_TRUSTED_ORIGINS")
)

DATABASE_URL = require_url_scheme("DATABASE_URL", env("DATABASE_URL"), {"postgres", "postgresql"})
DATABASES = {"default": env.db_url_config(DATABASE_URL)}
DATABASES["default"].update(
    {
        "CONN_MAX_AGE": env.int("DATABASE_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": env.int("DATABASE_CONNECT_TIMEOUT", default=5)},
    }
)
REDIS_URL = require_url_scheme("REDIS_URL", env("REDIS_URL"), {"redis", "rediss"})
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=None)
if CELERY_RESULT_BACKEND:
    require_url_scheme("CELERY_RESULT_BACKEND", CELERY_RESULT_BACKEND, {"redis", "rediss"})
CELERY_TASK_IGNORE_RESULT = CELERY_RESULT_BACKEND is None

DEBUG = False
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = env.bool("DJANGO_USE_X_FORWARDED_HOST", default=False)
