"""Circuit breaker for LLM failover — prevents infinite retry loops.

Tracks failures per model and opens the circuit after N consecutive failures
within a time window, with automatic half-open after cooldown.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class CircuitBreaker:
    """Per-model circuit breaker to prevent infinite failover loops.

    States:
        CLOSED: Normal operation, requests pass through.
        OPEN: Too many failures, requests are blocked.
        HALF_OPEN: After cooldown, one request is allowed to test the waters.

    Args:
        failure_threshold: Number of consecutive failures to open the circuit.
        cooldown_seconds: Time to wait before moving from OPEN to HALF_OPEN.
    """

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 60.0):
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._state: dict[str, str] = {}
        self._failure_count: dict[str, int] = {}
        self._last_failure: dict[str, float] = {}
        self._lock = threading.Lock()

    def get_state(self, model: str) -> str:
        """Get the current circuit state for a model."""
        with self._lock:
            state = self._state.get(model, self.CLOSED)
            if state == self.OPEN:
                last_fail = self._last_failure.get(model, 0)
                if time.time() - last_fail > self._cooldown:
                    self._state[model] = self.HALF_OPEN
                    return self.HALF_OPEN
            return state

    def record_failure(self, model: str) -> None:
        """Record a failure for a model. May open the circuit."""
        with self._lock:
            now = time.time()
            self._last_failure[model] = now
            self._failure_count[model] = self._failure_count.get(model, 0) + 1
            if self._failure_count[model] >= self._failure_threshold:
                self._state[model] = self.OPEN

    def record_success(self, model: str) -> None:
        """Record a success for a model. Resets failure count and closes circuit."""
        with self._lock:
            self._failure_count.pop(model, None)
            self._last_failure.pop(model, None)
            self._state.pop(model, None)

    def is_available(self, model: str) -> bool:
        """Check if a model is available (not OPEN)."""
        return self.get_state(model) != self.OPEN

    def all_models_available(self, models: list[str]) -> bool:
        """Check if at least one model in the list is available."""
        return any(self.is_available(m) for m in models)

    def reset(self, model: str) -> None:
        """Manually reset circuit for a model."""
        self.record_success(model)


# ── Container-aware helpers (migration to DI) ──────────────────────

def get_breaker_from_container() -> CircuitBreaker:
    """Get circuit breaker from the default DI container."""
    from src.llm.container import get_container
    return get_container().get_circuit_breaker()


# Global singleton for convenience (will be migrated to DI)
_breaker = CircuitBreaker()


def get_breaker() -> CircuitBreaker:
    """Get the global CircuitBreaker singleton.

    Prefers the DI container if available, falls back to module singleton.
    """
    try:
        return get_breaker_from_container()
    except Exception:
        return _breaker
