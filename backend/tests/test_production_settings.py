import os
import subprocess
import sys

import pytest


def load_production_settings(extra_environment):
    environment = os.environ.copy()
    environment.update(extra_environment)
    environment["DJANGO_SETTINGS_MODULE"] = "config.settings.production"
    return subprocess.run(
        [sys.executable, "manage.py", "check"],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
    )


@pytest.fixture
def safe_production_environment():
    return {
        "DJANGO_SECRET_KEY": "s" * 64,
        "DJANGO_ALLOWED_HOSTS": "api.example.com",
        "DJANGO_CORS_ALLOWED_ORIGINS": "https://app.example.com",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://app.example.com",
        "DATABASE_URL": "postgresql://user:password@db.example.com:5432/app",
        "REDIS_URL": "rediss://redis.example.com:6379/0",
    }


def test_production_settings_accept_safe_environment(safe_production_environment):
    result = load_production_settings(safe_production_environment)

    assert result.returncode == 0, result.stderr
    assert "System check identified no issues" in result.stdout


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DJANGO_SECRET_KEY", "short"),
        ("DJANGO_ALLOWED_HOSTS", "*"),
        ("DJANGO_CSRF_TRUSTED_ORIGINS", "http://app.example.com"),
        ("DATABASE_URL", "sqlite:///db.sqlite3"),
        ("REDIS_URL", "http://redis.example.com"),
    ],
)
def test_production_settings_reject_unsafe_environment(safe_production_environment, name, value):
    safe_production_environment[name] = value

    result = load_production_settings(safe_production_environment)

    assert result.returncode != 0
    assert "ImproperlyConfigured" in result.stderr
