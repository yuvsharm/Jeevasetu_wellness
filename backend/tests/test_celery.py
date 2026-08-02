from config.celery import app, configuration_is_ready
from config.tasks import infrastructure_check


def test_celery_uses_safe_infrastructure_defaults(settings):
    assert configuration_is_ready() is True
    assert app.conf.task_serializer == "json"
    assert app.conf.result_serializer == "json"
    assert app.conf.accept_content == ["json"]
    assert app.conf.enable_utc is True
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert settings.CELERY_RESULT_BACKEND is None
    assert settings.CELERY_TASK_IGNORE_RESULT is True
    assert settings.CELERY_BEAT_SCHEDULE == {}


def test_infrastructure_task_is_side_effect_free():
    assert infrastructure_check.run() == {"status": "ok"}
    assert infrastructure_check.ignore_result is True
