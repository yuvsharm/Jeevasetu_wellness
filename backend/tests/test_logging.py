import json
import logging

from config.logging import JsonFormatter, SensitiveDataFilter


def format_record(message, args=()):
    record = logging.LogRecord("test", logging.INFO, __file__, 1, message, args, None)
    SensitiveDataFilter().filter(record)
    return json.loads(JsonFormatter().format(record))


def test_json_logging_has_minimal_structured_fields():
    event = format_record("service ready")

    assert event["level"] == "INFO"
    assert event["logger"] == "test"
    assert event["message"] == "service ready"
    assert "timestamp" in event


def test_json_logging_redacts_sensitive_values():
    event = format_record("authorization=Bearer-secret password=hunter2 otp=123456")

    assert "Bearer-secret" not in event["message"]
    assert "hunter2" not in event["message"]
    assert "123456" not in event["message"]
    assert event["message"].count("[REDACTED]") == 3


def test_json_logging_redacts_sensitive_mapping_arguments():
    event = format_record("payload=%s", {"token": "private-token", "safe": "value"})

    assert "private-token" not in event["message"]
    assert "[REDACTED]" in event["message"]


def test_json_logging_redacts_authorization_and_cookie_headers():
    event = format_record("Authorization: Bearer abc.def.ghi")
    cookie_event = format_record("Cookie: sessionid=private; csrftoken=private")

    assert "abc.def.ghi" not in event["message"]
    assert "sessionid" not in cookie_event["message"]
    assert "csrftoken" not in cookie_event["message"]
