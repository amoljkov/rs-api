import json
from typing import Any

SENSITIVE_KEYS = {
    "authorization",
    "email",
    "jwe",
    "phone",
    "private_key",
    "private_key_b64",
    "public-token",
    "signature",
    "token",
}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if str(key).lower() in SENSITIVE_KEYS:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "...(truncated)"


def format_json_for_log(payload: Any, *, max_len: int = 2000) -> str:
    try:
        redacted = _redact(payload)
        return _truncate(json.dumps(redacted, ensure_ascii=False), max_len)
    except (TypeError, ValueError):
        return _truncate(str(payload), max_len)


def format_response_text(body_text: str, *, max_len: int = 2000) -> str:
    if not body_text:
        return ""
    try:
        parsed = json.loads(body_text)
        redacted = _redact(parsed)
        return _truncate(json.dumps(redacted, ensure_ascii=False), max_len)
    except (TypeError, ValueError, json.JSONDecodeError):
        return _truncate(body_text, max_len)
