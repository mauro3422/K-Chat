"""Observability state for node failover decisions."""

from __future__ import annotations

import time
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class FailoverState:
    required_misses: int = 2
    miss_count: int = 0
    last_check_at: float = 0.0
    last_primary_seen_at: float = 0.0
    last_promotion_at: float = 0.0
    last_action: str = "idle"
    last_reason: str = ""
    promoted_role: str = ""

    def snapshot(self) -> dict[str, Any]:
        return {
            "required_misses": self.required_misses,
            "miss_count": self.miss_count,
            "last_check_at": self.last_check_at,
            "last_primary_seen_at": self.last_primary_seen_at,
            "last_promotion_at": self.last_promotion_at,
            "last_action": self.last_action,
            "last_reason": self.last_reason,
            "promoted_role": self.promoted_role,
            "should_promote": self.miss_count >= self.required_misses,
        }

    def note_check(self, *, primary_seen: bool, reason: str = "") -> None:
        self.last_check_at = time.time()
        self.last_reason = reason
        if primary_seen:
            self.last_primary_seen_at = self.last_check_at
            self.miss_count = 0
            self.last_action = "primary_seen"
            return
        self.miss_count += 1
        self.last_action = "primary_missing"

    def note_promotion(self, role: str = "primary", reason: str = "leader_election") -> None:
        self.last_promotion_at = time.time()
        self.last_action = "promoted"
        self.last_reason = reason
        self.promoted_role = role
        self.miss_count = 0

    def reset(self, reason: str = "reset") -> None:
        self.miss_count = 0
        self.last_action = "reset"
        self.last_reason = reason


_current_failover_state: ContextVar[FailoverState | None] = ContextVar("kairos_failover_state", default=None)


def configure_failover_state(state: FailoverState | None) -> None:
    _current_failover_state.set(state)


def reset_failover_state() -> None:
    _current_failover_state.set(None)


def get_failover_state() -> FailoverState:
    state = _current_failover_state.get()
    if state is None:
        state = FailoverState()
        _current_failover_state.set(state)
    return state
