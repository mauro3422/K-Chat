import re
from collections.abc import Mapping

ERROR_MESSAGES = {
    "rate_limit": "Respuesta interrumpida por rate limit. Espera un momento antes de reintentar.",
    "timeout": "The model took too long to respond.",
    "network": "Connection error with the model.",
    "tool_error": "A tool or function call failed. Please try again.",
    "model": "The model encountered an error. Please try again.",
    "unknown": "An unexpected error occurred. Please try again.",
}

_DURATION_RE = re.compile(r"^\s*(?:(\d+)s|(?:(\d+)m)?(?:(\d+)s)?)\s*$", re.IGNORECASE)


def _extract_headers(error: Exception | str) -> Mapping[str, str]:
    if isinstance(error, str):
        return {}
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        return headers
    return {}


def _parse_duration_value(value: str | None) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return int(text)

    match = _DURATION_RE.match(text)
    if not match:
        return None

    if match.group(1):
        return int(match.group(1))

    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    return minutes * 60 + seconds


def _format_duration_hint(seconds: int | None) -> str | None:
    if seconds is None:
        return None
    if seconds <= 0:
        return None
    minutes, remaining = divmod(seconds, 60)
    parts: list[str] = []
    if minutes:
        parts.append(f"{minutes}m")
    if remaining or not parts:
        parts.append(f"{remaining}s")
    return "".join(parts)


def _extract_rate_limit_hint(error: Exception | str) -> str | None:
    headers = _extract_headers(error)
    if not headers:
        return None

    raw_hints: list[str] = []
    numeric_hints: list[int] = []

    for key in ("retry-after", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
        value = headers.get(key) or headers.get(key.lower()) or headers.get(key.upper())
        if not value:
            continue
        parsed = _parse_duration_value(str(value))
        if parsed is not None:
            numeric_hints.append(parsed)
        else:
            raw_hints.append(str(value).strip())

    if numeric_hints:
        return _format_duration_hint(max(numeric_hints))
    if raw_hints:
        return raw_hints[0]
    return None


def classify_error(error: Exception | str) -> tuple[str, str]:
    """Classifies an error message into a type and a user-friendly message."""
    error_msg = str(error)
    msg_l = error_msg.lower()
    if "rate limit" in msg_l or "ratelimit" in msg_l or "429" in msg_l:
        hint = _extract_rate_limit_hint(error)
        msg = ERROR_MESSAGES["rate_limit"]
        if hint:
            msg = f"{msg} Reintenta en ~{hint}."
        return "rate_limit", msg
    elif "timeout" in msg_l:
        return "timeout", ERROR_MESSAGES["timeout"]
    elif "connection" in msg_l or "network" in msg_l:
        return "network", ERROR_MESSAGES["network"]
    elif "tool" in msg_l or "function" in msg_l:
        return "tool_error", ERROR_MESSAGES["tool_error"]
    elif "model" in msg_l or "api" in msg_l:
        return "model", ERROR_MESSAGES["model"]
    return "unknown", ERROR_MESSAGES["unknown"]
