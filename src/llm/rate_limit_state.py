"""Thread-safe tracker for per-model rate limit state.

Lego block: independent, no framework imports, pure Python.
Can be used by any layer that needs to know which models are
currently rate limited and when they'll recover.
"""

from __future__ import annotations

import threading
import time
from typing import Any


class ModelRateLimitStore:
    """Tracks rate-limited models and their cooldown expiration.

    Thread-safe (Lock). Pure Python, no framework deps.
    Also tracks models confirmed working (available) so the UI
    can show live status without guessing.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # model_id -> expiration_timestamp (time.monotonic)
        self._limited: dict[str, float] = {}
        # model_id -> last error detail
        self._details: dict[str, str] = {}
        # model_ids confirmed working (survives clear)
        self._available: set[str] = set()
        # model_ids confirmed dead (promotion ended, removed, etc.)
        self._unavailable: set[str] = set()

    # --- Public API ---------------------------------------------------

    def mark_rate_limited(self, model_id: str, retry_after: float = 60.0, detail: str = "") -> None:
        """Record that a model is rate limited until ``retry_after`` seconds from now."""
        expires = time.monotonic() + retry_after
        with self._lock:
            self._limited[model_id] = expires
            if detail:
                self._details[model_id] = detail
            self._available.discard(model_id)

    def clear_rate_limit(self, model_id: str) -> None:
        """Manually clear a rate limit (e.g. after a successful call)."""
        with self._lock:
            self._limited.pop(model_id, None)
            self._details.pop(model_id, None)

    def mark_available(self, model_id: str) -> None:
        """Confirm a model works (e.g. after a successful ping or user call)."""
        with self._lock:
            self._available.add(model_id)
            self._limited.pop(model_id, None)
            self._details.pop(model_id, None)
            self._unavailable.discard(model_id)

    def mark_unavailable(self, model_id: str) -> None:
        """Mark a model as permanently unavailable (promotion ended, removed, etc.)."""
        with self._lock:
            self._unavailable.add(model_id)
            self._available.discard(model_id)
            self._limited.pop(model_id, None)
            self._details.pop(model_id, None)

    def is_available(self, model_id: str) -> bool:
        """Has this model been confirmed working since last restart?"""
        with self._lock:
            return model_id in self._available

    def is_unavailable(self, model_id: str) -> bool:
        """Is this model permanently unavailable (promotion ended, etc.)?"""
        with self._lock:
            return model_id in self._unavailable

    def is_rate_limited(self, model_id: str) -> bool:
        """Check if a model is currently rate limited (cooldown still active)."""
        with self._lock:
            expires = self._limited.get(model_id)
            if expires is None:
                return False
            if time.monotonic() >= expires:
                del self._limited[model_id]
                self._details.pop(model_id, None)
                return False
            return True

    def get_cooldown_remaining(self, model_id: str) -> float | None:
        """Seconds remaining until the model can be used again, or None if not limited."""
        with self._lock:
            expires = self._limited.get(model_id)
            if expires is None:
                return None
            remaining = expires - time.monotonic()
            if remaining <= 0:
                del self._limited[model_id]
                self._details.pop(model_id, None)
                return None
            return remaining

    def get_all_rate_limited(self) -> dict[str, dict[str, Any]]:
        """Return all currently-limited models with cooldown info."""
        now = time.monotonic()
        result: dict[str, dict[str, Any]] = {}
        with self._lock:
            expired = [mid for mid, exp in self._limited.items() if now >= exp]
            for mid in expired:
                self._limited.pop(mid, None)
                self._details.pop(mid, None)
            for model_id, expires in self._limited.items():
                result[model_id] = {
                    "cooldown_remaining": round(expires - now, 1),
                    "detail": self._details.get(model_id, ""),
                }
        return result

    def summary(self) -> dict[str, Any]:
        """Human-readable summary of rate limit state."""
        limited = self.get_all_rate_limited()
        return {
            "limited_count": len(limited),
            "available_models": sorted(self._available),
            "unavailable_models": sorted(self._unavailable),
            "limited_models": limited,
        }


# --- Global singleton (for convenience, can be injected) --------------
_RATE_LIMIT_STORE: ModelRateLimitStore | None = None
_lock = threading.Lock()


def get_rate_limit_store() -> ModelRateLimitStore:
    """Get or create the global rate limit store (lazy singleton)."""
    global _RATE_LIMIT_STORE
    if _RATE_LIMIT_STORE is None:
        with _lock:
            if _RATE_LIMIT_STORE is None:
                _RATE_LIMIT_STORE = ModelRateLimitStore()
    return _RATE_LIMIT_STORE
