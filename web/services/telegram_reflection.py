"""Telegram reflection state for observability across UI instances."""

from __future__ import annotations

import time
from collections import deque
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class TelegramReflectionEvent:
    path: str
    event_type: str
    session_id: str = ""
    local_published: bool = False
    lan_sent: int = 0
    lan_failed: int = 0
    last_error: str = ""
    source: dict[str, Any] = field(default_factory=dict)
    seen_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "local_published": self.local_published,
            "lan_sent": self.lan_sent,
            "lan_failed": self.lan_failed,
            "last_error": self.last_error,
            "source": dict(self.source),
            "seen_at": self.seen_at,
        }


class TelegramReflectionState:
    """Keeps a lightweight observability trail for reflected Telegram events."""

    def __init__(self, *, max_events: int = 25) -> None:
        self._events: deque[TelegramReflectionEvent] = deque(maxlen=max_events)
        self._last_event: TelegramReflectionEvent | None = None

    def record(
        self,
        event_type: str,
        event_data: dict[str, Any] | None = None,
        *,
        path: str,
        local_published: bool = False,
        lan_sent: int = 0,
        lan_failed: int = 0,
        last_error: str = "",
    ) -> TelegramReflectionEvent:
        data = dict(event_data or {})
        event = TelegramReflectionEvent(
            path=path,
            event_type=event_type,
            session_id=str(data.get("session_id", "")),
            local_published=local_published,
            lan_sent=lan_sent,
            lan_failed=lan_failed,
            last_error=last_error,
            source=dict(data.get("source", {})) if isinstance(data.get("source", {}), dict) else {},
        )
        self._events.append(event)
        self._last_event = event
        return event

    def snapshot(self) -> dict[str, Any]:
        last = self._last_event.to_dict() if self._last_event else None
        recent = [event.to_dict() for event in self._events]
        lan_total_sent = sum(event.lan_sent for event in self._events)
        lan_total_failed = sum(event.lan_failed for event in self._events)
        return {
            "last_event": last,
            "recent_events": recent,
            "recent_count": len(recent),
            "lan_total_sent": lan_total_sent,
            "lan_total_failed": lan_total_failed,
            "has_recent_reflection": self._last_event is not None,
        }


_current_telegram_reflection_state: ContextVar[TelegramReflectionState | None] = ContextVar(
    "kairos_telegram_reflection_state",
    default=None,
)


def configure_telegram_reflection_state(state: TelegramReflectionState | None) -> None:
    _current_telegram_reflection_state.set(state)


def reset_telegram_reflection_state() -> None:
    _current_telegram_reflection_state.set(None)


def get_telegram_reflection_state() -> TelegramReflectionState:
    state = _current_telegram_reflection_state.get()
    if state is None:
        state = TelegramReflectionState()
        _current_telegram_reflection_state.set(state)
    return state
