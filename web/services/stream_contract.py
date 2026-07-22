"""Shared contract for NDJSON stream events."""

from __future__ import annotations

import json
from typing import Any

STREAM_EVENT_TYPES = frozenset({
    "heartbeat",
    "content",
    "reasoning",
    "tool_call",
    "error",
    "memory",
    "notification",
    "retry",
})


def build_stream_event(event_type: str, data: Any) -> dict[str, Any]:
    if event_type not in STREAM_EVENT_TYPES:
        raise ValueError(f"Unsupported stream event type: {event_type}")
    return {"t": event_type, "d": data}


def serialize_stream_event(event_type: str, data: Any) -> str:
    return json.dumps(build_stream_event(event_type, data), ensure_ascii=False) + "\n"
