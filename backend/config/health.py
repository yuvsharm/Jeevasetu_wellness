from django.db import connection
from django.db.utils import DatabaseError
from drf_spectacular.utils import extend_schema, inline_serializer
from redis import Redis
from redis.exceptions import RedisError
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from config.celery import configuration_is_ready

StatusSerializer = inline_serializer(
    name="InfrastructureHealth",
    fields={
        "status": serializers.ChoiceField(choices=["ok", "unavailable"]),
        "component": serializers.CharField(required=False),
    },
)


def database_status():
    try:
        connection.ensure_connection()
    except DatabaseError:
        return False
    return True


def redis_status():
    from django.conf import settings

    try:
        client = Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
        )
        return bool(client.ping())
    except (RedisError, OSError, ValueError):
        return False


def component_response(component, available):
    state = "ok" if available else "unavailable"
    http_status = status.HTTP_200_OK if available else status.HTTP_503_SERVICE_UNAVAILABLE
    return Response({"status": state, "component": component}, status=http_status)


class InfrastructureView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]


class LivenessView(InfrastructureView):
    @extend_schema(responses={200: StatusSerializer})
    def get(self, request):
        return component_response("application", True)


class DatabaseReadinessView(InfrastructureView):
    @extend_schema(responses={200: StatusSerializer, 503: StatusSerializer})
    def get(self, request):
        return component_response("database", database_status())


class RedisReadinessView(InfrastructureView):
    @extend_schema(responses={200: StatusSerializer, 503: StatusSerializer})
    def get(self, request):
        return component_response("redis", redis_status())


class CeleryReadinessView(InfrastructureView):
    @extend_schema(responses={200: StatusSerializer, 503: StatusSerializer})
    def get(self, request):
        return component_response("celery", configuration_is_ready())


class ReadinessView(InfrastructureView):
    @extend_schema(responses={200: StatusSerializer, 503: StatusSerializer})
    def get(self, request):
        components = {
            "database": database_status(),
            "redis": redis_status(),
            "celery": configuration_is_ready(),
        }
        available = all(components.values())
        state = "ok" if available else "unavailable"
        http_status = status.HTTP_200_OK if available else status.HTTP_503_SERVICE_UNAVAILABLE
        safe_components = {
            name: "ok" if ready else "unavailable" for name, ready in components.items()
        }
        return Response({"status": state, "components": safe_components}, status=http_status)
