from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env

DEBUG = env.bool("DJANGO_DEBUG", default=True)
SECRET_KEY = env("DJANGO_SECRET_KEY", default="unsafe-local-development-key")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "backend"])
DATABASE_URL = env("DATABASE_URL")
if urlparse(DATABASE_URL).scheme not in {"postgres", "postgresql"}:
    raise ImproperlyConfigured("DATABASE_URL must use PostgreSQL in development")
DATABASES = {"default": env.db_url_config(DATABASE_URL)}
DATABASES["default"].update(
    {
        "CONN_MAX_AGE": env.int("DATABASE_CONN_MAX_AGE", default=60),
        "CONN_HEALTH_CHECKS": True,
        "OPTIONS": {"connect_timeout": env.int("DATABASE_CONNECT_TIMEOUT", default=5)},
    }
)
REDIS_URL = env("REDIS_URL")
if urlparse(REDIS_URL).scheme not in {"redis", "rediss"}:
    raise ImproperlyConfigured("REDIS_URL must use Redis in development")
CELERY_BROKER_URL = REDIS_URL
AUTH_RATE_LIMIT_REDIS_URL = env(
    "AUTH_RATE_LIMIT_REDIS_URL", default=f"{REDIS_URL.rsplit('/', 1)[0]}/1"
)
if urlparse(AUTH_RATE_LIMIT_REDIS_URL).scheme not in {"redis", "rediss"}:
    raise ImproperlyConfigured("AUTH_RATE_LIMIT_REDIS_URL must use Redis in development")
CACHES["default"]["LOCATION"] = AUTH_RATE_LIMIT_REDIS_URL  # noqa: F405
CORS_ALLOWED_ORIGINS = env.list(  # noqa: F405
    "DJANGO_CORS_ALLOWED_ORIGINS", default=["http://localhost:3000"]
)
CSRF_TRUSTED_ORIGINS = env.list(  # noqa: F405
    "DJANGO_CSRF_TRUSTED_ORIGINS", default=["http://localhost:3000"]
)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += [  # noqa: F405
    "rest_framework.renderers.BrowsableAPIRenderer"
]
