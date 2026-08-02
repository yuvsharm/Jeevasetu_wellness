import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(password|passwd|otp|token|secret|cookie|authorization|api[_-]?key)"
)
AUTHORIZATION_VALUE_PATTERN = re.compile(
    r"(?i)\b(authorization)(\s*[:=]\s*)((?:bearer|basic)\s+[^\s,;]+|[^\s,;]+)"
)
COOKIE_VALUE_PATTERN = re.compile(r"(?i)\b(cookie)(\s*[:=]\s*)(.+)$")
SENSITIVE_VALUE_PATTERN = re.compile(
    r"(?i)\b(password|passwd|otp|token|secret|cookie|authorization|api[_-]?key)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if SENSITIVE_KEY_PATTERN.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact(item) for item in value)
    if isinstance(value, str):
        value = AUTHORIZATION_VALUE_PATTERN.sub(r"\1\2[REDACTED]", value)
        value = COOKIE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", value)
        return SENSITIVE_VALUE_PATTERN.sub(r"\1\2[REDACTED]", value)
    return value


class SensitiveDataFilter(logging.Filter):
    """Redact credential-like values before any formatter receives a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.msg)
        record.args = _redact(record.args)
        return True


class JsonFormatter(logging.Formatter):
    """Emit a minimal production-safe JSON log event."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = str(request_id)
        if record.exc_info:
            payload["exception"] = {"type": record.exc_info[0].__name__}
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
