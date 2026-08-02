from unittest.mock import Mock, patch

import pytest
from django.db.utils import OperationalError
from django.urls import reverse
from redis.exceptions import ConnectionError


def test_liveness_succeeds_without_dependency_checks(api_client):
    with patch("config.health.database_status") as database_check:
        response = api_client.get(reverse("health-live"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "application"}
    database_check.assert_not_called()


@pytest.mark.django_db
def test_database_readiness_succeeds(api_client):
    response = api_client.get(reverse("health-ready-database"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "database"}


def test_database_readiness_fails_safely(api_client):
    with patch(
        "config.health.connection.ensure_connection", side_effect=OperationalError("secret")
    ):
        response = api_client.get(reverse("health-ready-database"))

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "component": "database"}
    assert "secret" not in response.content.decode()


def test_redis_readiness_succeeds(api_client):
    client = Mock()
    client.ping.return_value = True
    with patch("config.health.Redis.from_url", return_value=client):
        response = api_client.get(reverse("health-ready-redis"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "redis"}


def test_redis_readiness_fails_safely(api_client):
    with patch("config.health.Redis.from_url", side_effect=ConnectionError("redis://secret")):
        response = api_client.get(reverse("health-ready-redis"))

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "component": "redis"}
    assert "secret" not in response.content.decode()


def test_celery_configuration_readiness(api_client):
    response = api_client.get(reverse("health-ready-celery"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "component": "celery"}


def test_aggregate_readiness_degrades_safely(api_client):
    with (
        patch("config.health.database_status", return_value=True),
        patch("config.health.redis_status", return_value=False),
        patch("config.health.configuration_is_ready", return_value=True),
    ):
        response = api_client.get(reverse("health-ready"))

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "components": {"database": "ok", "redis": "unavailable", "celery": "ok"},
    }
