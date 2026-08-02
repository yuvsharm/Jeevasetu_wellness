import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

app = Celery("jeevasetu")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


def configuration_is_ready():
    return bool(
        app.conf.broker_url
        and app.conf.task_serializer == "json"
        and app.conf.accept_content == ["json"]
        and app.conf.timezone
    )
