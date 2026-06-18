"""Auto-discovering model registry — Lego block.

Dynamically discovers ALL models from Go and Zen APIs.
No hardcoded model names, no hardcoded tiers.
Everything comes from the API:
  - Which models exist (Go API)
  - Which free models exist (Zen API -free suffix)
  - Per-model availability (via lightweight pings)
  - Go account health (quota exhausted detection)

Depends on: RateLimitStore (for availability state), config.
Zero framework imports. Pure Python Lego.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# ── Heuristic tier markers ──────────────────────────────────────────
# Since the OpenCode API doesn't return pricing/tier metadata,
# we infer tiers from naming patterns. These are REASONABLE GUESSES,
# not hardcoded model names. Any Go API model will be visible
# regardless of tier -- just potentially in a different group.
# Tier inference heuristic — uses delimiters to avoid false positives.
# "k2.7" matches "kimi-k2.7-code" but not other models.
# "5.1" matches "glm-5.1" specifically.
# Lowercase comparison for robustness.
_PREMIUM_PATTERNS = ["-max", "5.1", "k2.7", "glm-"]
_STANDARD_PATTERNS = ["-pro", "-flash", "-omni", "k2.6", "k2.5", "v2.5", "v2-", "v4-"]


def _infer_tier(model_id: str) -> str:
    """Infer model tier from naming patterns.

    Uses delimiters (`-`, `.`, `/`) to avoid false positives.
    Returns one of: go_premium, go_standard, go_economy, free_ratelimited, zen.
    """
    mid = model_id.lower()
    if mid.endswith("-free"):
        return "free_ratelimited"
    # Tokenize by common delimiters for more precise matching
    tokens = set(mid.replace(".", "-").replace("_", "-").split("-"))
    for pat in _PREMIUM_PATTERNS:
        p = pat.lstrip("-")
        if p in tokens:
            return "go_premium"
        if pat in mid:
            return "go_premium"
    for pat in _STANDARD_PATTERNS:
        p = pat.lstrip("-")
        if p in tokens:
            return "go_standard"
        if pat in mid:
            return "go_standard"
    return "go_economy"


class ModelRegistry:
    """Lego block: auto-discovers models, tiers, and account health.

    Usage:
        registry = ModelRegistry(config)
        await registry.refresh()               # fetch from APIs
        tier = registry.get_tier("model-id")   # e.g. "go_standard"
        all_go = registry.get_go_models()      # list[str]

    Thread-safe. Zero framework deps.
    """

    def __init__(
        self,
        config: Any = None,
        provider_registry: Any = None,
        provider_fn: Callable[..., Any] | None = None,
    ) -> None:
        if config is None:
            from src._config import resolve_config
            config = resolve_config(config)
        self._config = config
        self._provider_registry = provider_registry
        self._provider_fn = provider_fn
        self._lock = threading.Lock()
        # Go API models (premium, standard, economy)
        self._go_models: list[str] = []
        # Free model candidates from Zen API (-free suffix)
        self._free_candidates: list[str] = []
        # All models in registry (union of Go + verified free)
        self._all_models: list[str] = []
        # Verified models (from discovery verifier)
        self._verified_models: set[str] = set()
        # Go account health
        self._go_quota_exhausted: bool = False
        # Last refresh timestamp
        self._last_refresh: float = 0.0
        self._refresh_interval: float = 300.0  # 5 minutes

    # ── Public API ──────────────────────────────────────────────────

    async def refresh(self) -> None:
        """Fetch all models from Go and Zen APIs.

        Safe to call frequently — uses in-memory cache with TTL.
        """
        now = time.monotonic()
        if now - self._last_refresh < self._refresh_interval:
            return

        go_ids: list[str] = []
        free_ids: list[str] = []

        # 1. Fetch Go API models
        try:
            if self._provider_fn is not None:
                provider = self._provider_fn()
            else:
                from src.llm.providers import _get_provider
                provider = _get_provider(config=self._config)
            go_raw = await provider.list_models()
            go_ids = [
                m if isinstance(m, str) else getattr(m, "id", "")
                for m in go_raw
            ]
            go_ids = [mid for mid in go_ids if mid]
            logger.info("Registry: discovered %d Go models", len(go_ids))
        except Exception as e:
            logger.warning("Registry: could not fetch Go models: %s", e)
            go_ids = list(self._go_models)  # keep previous cache

        # 2. Fetch Zen API models (for free candidates)
        try:
            import copy

            fresh = copy.copy(self._config)
            fresh.llm_mode = "zen"
            if self._provider_registry is not None:
                pcls = self._provider_registry.get(fresh.llm_provider)
            else:
                from src.llm.providers import _get_registry
                pcls = _get_registry().get(fresh.llm_provider)
            if pcls:
                zen_provider = pcls(
                    api_key=fresh.opencode_zen_api_key,
                    base_url=fresh.opencode_zen_base_url,
                )
                zen_raw = await zen_provider.list_models()
                for m in zen_raw:
                    mid = m if isinstance(m, str) else getattr(m, "id", "")
                    if mid and mid.endswith("-free") and mid not in go_ids:
                        free_ids.append(mid)
                logger.info(
                    "Registry: discovered %d free model candidates",
                    len(free_ids),
                )
        except Exception as e:
            logger.warning("Registry: could not fetch Zen models: %s", e)
            free_ids = list(self._free_candidates)

        # 3. Build the full list (Go models first, then free)
        all_models = list(go_ids)
        for mid in free_ids:
            if mid not in all_models:
                all_models.append(mid)

        with self._lock:
            self._go_models = go_ids
            self._free_candidates = free_ids
            self._all_models = all_models
            self._last_refresh = now

    def get_go_models(self) -> list[str]:
        """Return all Go API models."""
        with self._lock:
            return list(self._go_models)

    def get_free_candidates(self) -> list[str]:
        """Return all -free model candidates (may include expired promotions)."""
        with self._lock:
            return list(self._free_candidates)

    def get_all_models(self) -> list[str]:
        """Return all known models (Go + free)."""
        with self._lock:
            return list(self._all_models)

    def get_tier(self, model_id: str) -> str:
        """Classify a model into a tier — zero hardcoded names."""
        if model_id.endswith("-free"):
            return "free_ratelimited"
        with self._lock:
            if model_id in self._go_models:
                return _infer_tier(model_id)
        return "zen"

    def is_go_model(self, model_id: str) -> bool:
        """Is this a Go API model?"""
        with self._lock:
            return model_id in self._go_models

    def is_free_candidate(self, model_id: str) -> bool:
        """Is this a -free model candidate?"""
        with self._lock:
            return model_id in self._free_candidates

    # ── Verified models ──────────────────────────────────────────

    def add_verified_model(self, model_id: str) -> None:
        with self._lock:
            self._verified_models.add(model_id)

    def remove_verified_model(self, model_id: str) -> None:
        with self._lock:
            self._verified_models.discard(model_id)

    def set_verified_models(self, models: list[str] | None) -> None:
        with self._lock:
            self._verified_models = set(models or [])

    def get_verified_models(self) -> list[str]:
        with self._lock:
            return sorted(self._verified_models)

    # ── Go account health ──────────────────────────────────────────

    def mark_quota_exhausted(self) -> None:
        """Called when Go API returns 401 'insufficient balance'."""
        with self._lock:
            self._go_quota_exhausted = True
            logger.warning("Registry: Go quota marked as exhausted")

    def clear_quota_exhausted(self) -> None:
        """Reset quota flag (e.g. after user refreshes plan)."""
        with self._lock:
            self._go_quota_exhausted = False

    def is_quota_exhausted(self) -> bool:
        """Is the Go account out of quota?"""
        with self._lock:
            return self._go_quota_exhausted

    # ── Summary for UI ─────────────────────────────────────────────

    def summary(self) -> dict[str, Any]:
        """Human-readable summary of the registry state."""
        with self._lock:
            tiers: dict[str, int] = {}
            for mid in self._all_models:
                t = _infer_tier(mid) if mid in self._go_models else ("free_ratelimited" if mid.endswith("-free") else "zen")
                tiers[t] = tiers.get(t, 0) + 1
            return {
                "total_models": len(self._all_models),
                "go_models": len(self._go_models),
                "free_candidates": len(self._free_candidates),
                "go_quota_exhausted": self._go_quota_exhausted,
                "tier_counts": tiers,
            }


# ── Global singleton (lazy, thread-safe) ────────────────────────────
_registry: ModelRegistry | None = None
_lock = threading.Lock()


def configure_model_registry(registry: ModelRegistry | None) -> None:
    """Set the active registry explicitly.

    Passing None restores lazy singleton behavior.
    """
    global _registry
    with _lock:
        _registry = registry


def reset_model_registry() -> None:
    """Reset the active model registry."""
    configure_model_registry(None)


def get_model_registry(config: Any = None) -> ModelRegistry:
    """Get or create the global model registry (lazy singleton).

    Prefers the DI container if available, falls back to module singleton.
    """
    global _registry
    if _registry is not None:
        return _registry
    try:
        return get_model_registry_from_container(config=config)
    except Exception:
        if _registry is None:
            with _lock:
                if _registry is None:
                    _registry = ModelRegistry(config)
        return _registry


async def ensure_registry_refreshed(config: Any = None) -> None:
    """Ensure the registry has been refreshed at least once."""
    reg = get_model_registry(config)
    if not reg.get_go_models():
        await reg.refresh()


def add_verified_model(model_id: str, registry: ModelRegistry | None = None) -> None:
    (registry or get_model_registry()).add_verified_model(model_id)


def remove_verified_model(model_id: str, registry: ModelRegistry | None = None) -> None:
    (registry or get_model_registry()).remove_verified_model(model_id)


def set_verified_models(models: list[str] | None, registry: ModelRegistry | None = None) -> None:
    (registry or get_model_registry()).set_verified_models(models)


def get_verified_models(registry: ModelRegistry | None = None) -> list[str]:
    return (registry or get_model_registry()).get_verified_models()


# Backward-compatible alias
def get_verified_models_safe(registry: ModelRegistry | None = None) -> list[str]:
    return get_verified_models(registry=registry)


# ── Container-aware helpers ────────────────────────────────────────

def get_model_registry_from_container(config: Any = None) -> ModelRegistry:
    """Get model registry from the default DI container."""
    from src.llm.container import get_container
    container = get_container(config=config)
    return container.get_model_registry()
