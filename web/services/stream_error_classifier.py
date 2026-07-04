import re
from collections.abc import Mapping

ERROR_MESSAGES = {
    "rate_limit": "Request interrupted by rate limit. Please wait a moment before retrying.",
    "timeout": "The model took too long to respond.",
    "network": "Connection error with the model.",
    "tool_error": "A tool or function call failed. Please try again.",
    "model": "The model encountered an error. Please try again.",
    "bad_request": "The request was rejected by the provider. The message might be too long or malformed.",
    "credits": "Saldo insuficiente en la cuenta de Go/OpenCode. Recargá saldo para seguir usando el modelo.",
    "auth": "Error de autenticación con el provider. Verificá la API key.",
    "unknown": "An unexpected error occurred. Please try again.",
}

_DURATION_RE = re.compile(
    r"^\s*(?:(\d+)m)?\s*(?:(\d+)s)?\s*$", re.IGNORECASE
)
_EXTRACT_NUMBERS_RE = re.compile(r"(\d+)")
# Some providers return epoch timestamps like "1677765200" for reset time
_MAX_REASONABLE_SECONDS = 3600  # 1 hour — anything above is likely a timestamp, not a duration
def _extract_headers(error: Exception | str) -> Mapping[str, str]:
    if isinstance(error, str):
        return {}
    response = getattr(error, "response", None)
    headers = getattr(response, "headers", None)
    if isinstance(headers, Mapping):
        return headers
def _parse_duration_value(value: str | None) -> int | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        num = int(text)
        # Epoch timestamps (e.g. "1677765200") or huge numbers — skip them
        if num > _MAX_REASONABLE_SECONDS:
            return None
        return num

    match = _DURATION_RE.match(text)
    if not match:
        return None

    minutes = int(match.group(1) or 0)
    seconds = int(match.group(2) or 0)
    total = minutes * 60 + seconds
    # Cap at 1 hour — anything above is garbage data
    if total > _MAX_REASONABLE_SECONDS:
        return None
    return total


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
    # Bad request / invalid request — non-retryable (4xx client errors)
    if "bad request" in msg_l or "400" in msg_l or "invalid_request_error" in msg_l:
        return "bad_request", ERROR_MESSAGES["bad_request"]
    # Credits / billing / auth — non-retryable
    if any(x in msg_l for x in ("creditserror", "insufficient balance", "insufficient_balance",
                                  "usage limit reached", "goUsageLimit")):
        return "credits", ERROR_MESSAGES["credits"]
    if "401" in msg_l or "authenticationerror" in msg_l:
        return "auth", ERROR_MESSAGES["auth"]
    if "rate limit" in msg_l or "ratelimit" in msg_l or "429" in msg_l:
        ...
        hint = _extract_rate_limit_hint(error)
        # Detect free-tier quota exhaustion (OpenCode Zen specific)
        if "freeusagelimit" in msg_l or "free usage limit" in msg_l:
            msg = (
                "⏳ Cuota del modelo free agotada por hoy. "
                "Los modelos gratuitos tienen límites diarios de uso."
            )
            if hint:
                msg += f" Intentá en ~{hint}."
            else:
                msg += " Probá de nuevo en unos minutos o esperá a mañana."
            return "rate_limit", msg
        msg = ERROR_MESSAGES["rate_limit"]
        if hint:
            msg = f"{msg} Retry in ~{hint}."
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
