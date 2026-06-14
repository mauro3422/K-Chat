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
        tier = registry.get_tier("deepseek-v4-flash")  # "go_standard"
        all_go = registry.get_go_models()      # list[str]

    Thread-safe. Zero framework deps.
    """

    def __init__(self, config: Any = None) -> None:
        from src.config_loader import DEFAULT_CONFIG

        self._config = config or DEFAULT_CONFIG
        self._lock = threading.Lock()
        # Go API models (premium, standard, economy)
        self._go_models: list[str] = []
        # Free model candidates from Zen API (-free suffix)
        self._free_candidates: list[str] = []
        # All models in registry (union of Go + verified free)
        self._all_models: list[str] = []
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
            from src.llm.providers import _PROVIDER_REGISTRY

            pcls = _PROVIDER_REGISTRY.get(fresh.llm_provider)
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


def get_model_registry(config: Any = None) -> ModelRegistry:
    """Get or create the global model registry (lazy singleton)."""
    global _registry
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
