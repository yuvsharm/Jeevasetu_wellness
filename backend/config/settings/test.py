from .base import *  # noqa: F401,F403

SECRET_KEY = "test-only-secret-key"
DEBUG = False
ALLOWED_HOSTS = ["testserver", "localhost"]
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "OPTIONS": {},
    }
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CORS_ALLOWED_ORIGINS = []
CSRF_TRUSTED_ORIGINS = []
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_BROKER_URL = "memory://"
CELERY_RESULT_BACKEND = None
CELERY_TASK_IGNORE_RESULT = True
