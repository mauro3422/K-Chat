"""Tests for ModelRegistry — the dynamic model discovery Lego block.

Tests are organised in three layers:
  1. Pure functions: _infer_tier edge cases
  2. ModelRegistry unit: thread safety, quota, tier logic with mocked APIs
  3. Integration: singleton, refresh, error recovery

NOTE: All test methods are `async def` due to the root conftest having an
autouse=True async fixture (`setup_test_db`). Pytest asyncio strict mode
requires async markers for async fixtures.
"""

from __future__ import annotations

import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.anyio

from src.llm.model_registry import (
    ModelRegistry,
    _infer_tier,
    get_model_registry,
)


# ═══════════════════════════════════════════════════════════════════
# 1. _infer_tier  —  pure function, no mocks needed
# ═══════════════════════════════════════════════════════════════════


class TestInferTier:
    """Pure function tests — no state, no mocks, just logic."""

    # ── Premium patterns ──────────────────────────────────────────

    @pytest.mark.parametrize("model_id,expected", [
        ("qwen3.7-max", "go_premium"),
        ("deepseek-max-v2", "go_premium"),
        ("glm-5.1", "go_premium"),
        ("kimi-k2.7-code", "go_premium"),
        ("glm-5", "go_premium"),
        ("glm-5.1", "go_premium"),
    ])
    async def test_premium(self, model_id, expected):
        assert _infer_tier(model_id) == expected

    # ── Standard patterns ─────────────────────────────────────────

    @pytest.mark.parametrize("model_id,expected", [
        ("deepseek-v4-pro", "go_standard"),
        ("mimo-v2.5-pro", "go_standard"),
        ("mimo-v2-pro", "go_standard"),
        ("deepseek-v4-flash", "go_standard"),
        ("mimo-v2-omni", "go_standard"),
        ("kimi-k2.6", "go_standard"),
        ("kimi-k2.5", "go_standard"),
        ("mimo-v2.5", "go_standard"),
        ("mimo-v2-omni", "go_standard"),
        ("deepseek-v4-flash", "go_standard"),
    ])
    async def test_standard(self, model_id, expected):
        assert _infer_tier(model_id) == expected

    # ── Economy (fallback) ────────────────────────────────────────

    @pytest.mark.parametrize("model_id,expected", [
        ("minimax-m3", "go_economy"),
        ("minimax-m2.7", "go_economy"),
        ("minimax-m2.5", "go_economy"),
        ("qwen3.7-plus", "go_economy"),
        ("qwen3.6-plus", "go_economy"),
        ("qwen3.5-plus", "go_economy"),
        ("hy3-preview", "go_economy"),
    ])
    async def test_economy(self, model_id, expected):
        assert _infer_tier(model_id) == expected

    # ── Free models (suffix -free) ────────────────────────────────

    @pytest.mark.parametrize("model_id,expected", [
        ("deepseek-v4-flash-free", "free_ratelimited"),
        ("mimo-v2.5-free", "free_ratelimited"),
        ("nemotron-3-ultra-free", "free_ratelimited"),
    ])
    async def test_free(self, model_id, expected):
        assert _infer_tier(model_id) == expected

    # ── Edge cases ─────────────────────────────────────────────────

    @pytest.mark.parametrize("model_id,expected", [
        ("minimax-m3", "go_economy"),
        ("minimax-m2.7", "go_economy"),
        ("QWEN3.7-MAX", "go_premium"),
        ("DEEPSEEK-V4-FLASH", "go_standard"),
        ("future-model-x1", "go_economy"),
        ("unknown-v3", "go_economy"),
        ("my_custom_model-pro", "go_standard"),
        ("custom-v2.5-ultra", "go_standard"),
    ])
    async def test_edge_cases(self, model_id, expected):
        assert _infer_tier(model_id) == expected

    # ── Non-Go models (not tiered) ────────────────────────────────

    @pytest.mark.parametrize("model_id,expected", [
        ("qwen3.7-max-free", "free_ratelimited"),
        ("pro-model-free", "free_ratelimited"),
    ])
    async def test_free_takes_precedence(self, model_id, expected):
        """-free suffix returns free_ratelimited regardless of other patterns."""
        assert _infer_tier(model_id) == expected


# ═══════════════════════════════════════════════════════════════════
# 2. ModelRegistry  —  unit tests with mocked provider APIs
# ═══════════════════════════════════════════════════════════════════


class FakeProvider:
    """Simulates an LLM provider returning a fixed model list."""

    def __init__(self, models: list[str]) -> None:
        self.models = models

    async def list_models(self) -> list[str]:
        return self.models


@pytest.fixture
def registry():
    """Fresh ModelRegistry with empty state (dummy config)."""
    cfg = MagicMock()
    cfg.llm_mode = "go"
    cfg.opencode_api_key = "test-key"
    cfg.opencode_zen_api_key = "test-key"
    cfg.opencode_base_url = "https://example.com/v1"
    cfg.opencode_zen_base_url = "https://example.com/zen/v1"
    cfg.opencode_go_base_url = "https://example.com/go/v1"
    cfg.llm_provider = "openai"
    return ModelRegistry(config=cfg)


class TestModelRegistry:
    """Unit tests for ModelRegistry — mock the API calls."""

    # ── Initial state ─────────────────────────────────────────────

    async def test_initial_state(self, registry):
        assert registry.get_go_models() == []
        assert registry.get_free_candidates() == []
        assert registry.get_all_models() == []
        assert registry.is_quota_exhausted() is False

    # ── Refresh ───────────────────────────────────────────────────

    # The async refresh() imports _get_provider and _PROVIDER_REGISTRY
    # inside the method body, so we patch the source modules.

    @patch("src.llm.providers._get_provider")
    @patch("src.llm.providers._PROVIDER_REGISTRY", new_callable=dict)
    async def test_refresh_go_only(self, mock_registry, mock_get_provider, registry):
        """Only Go API models, no Zen API (no -free suffix)."""
        mock_get_provider.return_value = FakeProvider([
            "deepseek-v4-pro", "deepseek-v4-flash", "minimax-m3",
        ])
        mock_registry.clear()  # no Zen provider registered

        await registry.refresh()

        go = registry.get_go_models()
        assert len(go) == 3
        assert "deepseek-v4-pro" in go
        assert "deepseek-v4-flash" in go
        assert "minimax-m3" in go
        assert registry.get_free_candidates() == []
        assert registry.get_all_models() == go

    @patch("src.llm.providers._get_provider")
    @patch("src.llm.providers._PROVIDER_REGISTRY", new_callable=dict)
    async def test_refresh_with_free_models(
        self, mock_registry, mock_get_provider, registry
    ):
        """Go + Zen API with -free models."""
        mock_get_provider.return_value = FakeProvider([
            "deepseek-v4-flash", "minimax-m3",
        ])

        # Register a fake Zen provider class in the registry
        zen_provider = FakeProvider([
            "deepseek-v4-flash-free", "mimo-v2.5-free",
            "claude-sonnet-4", "gpt-5.4",
        ])
        mock_provider_cls = MagicMock()
        mock_provider_cls.return_value = zen_provider
        mock_registry["openai"] = mock_provider_cls

        await registry.refresh()

        go = registry.get_go_models()
        free = registry.get_free_candidates()
        all_m = registry.get_all_models()

        assert len(go) == 2
        assert "deepseek-v4-flash" in go
        assert "minimax-m3" in go

        assert len(free) == 2
        assert "deepseek-v4-flash-free" in free
        assert "mimo-v2.5-free" in free

        assert len(all_m) == 4
        assert "deepseek-v4-flash" in all_m
        assert "deepseek-v4-flash-free" in all_m

    @patch("src.llm.providers._get_provider")
    async def test_refresh_cache_ttl(self, mock_get_provider, registry):
        """Refresh respects TTL — does not re-fetch before interval."""
        mock_get_provider.return_value = FakeProvider(["model-a"])
        # First call: no cache, must refresh
        registry._refresh_interval = 0
        await registry.refresh()
        assert registry.get_go_models() == ["model-a"]

        # Second call: TTL not expired, should use cache
        mock_get_provider.return_value = FakeProvider(["model-b"])
        registry._refresh_interval = 999999
        registry._last_refresh = 0  # but wait, this clears the cache time...
        # Actually the issue is _last_refresh=0 means now-0 is huge.
        # Set it to a recent timestamp so TTL blocks
        import time
        registry._last_refresh = time.monotonic()
        await registry.refresh()
        assert registry.get_go_models() == ["model-a"]

    @patch("src.llm.providers._get_provider")
    async def test_refresh_error_falls_back_to_cache(
        self, mock_get_provider, registry
    ):
        """When API fails, keep previous model list."""
        mock_get_provider.return_value = FakeProvider(["model-a"])
        registry._refresh_interval = 0
        await registry.refresh()
        assert registry.get_go_models() == ["model-a"]

        mock_get_provider.side_effect = Exception("API down")
        registry._last_refresh = 0
        await registry.refresh()
        assert registry.get_go_models() == ["model-a"]

    # ── Tier classification ───────────────────────────────────────

    async def test_get_tier_go_model(self, registry):
        """Go models get their inferred tier (not 'zen')."""
        registry._go_models = ["qwen3.7-max", "deepseek-v4-flash", "minimax-m3"]
        assert registry.get_tier("qwen3.7-max") == "go_premium"
        assert registry.get_tier("deepseek-v4-flash") == "go_standard"
        assert registry.get_tier("minimax-m3") == "go_economy"

    async def test_get_tier_free_model(self, registry):
        """Free models get 'free_ratelimited' regardless of Go list."""
        registry._free_candidates = ["deepseek-v4-flash-free"]
        assert registry.get_tier("deepseek-v4-flash-free") == "free_ratelimited"

    async def test_get_tier_zen_model(self, registry):
        """Models not in Go and not -free return 'zen'."""
        registry._go_models = ["deepseek-v4-flash"]
        assert registry.get_tier("claude-sonnet-4") == "zen"
        assert registry.get_tier("gpt-5.4") == "zen"
        assert registry.get_tier("big-pickle") == "zen"

    async def test_get_tier_free_go_overlap(self, registry):
        """A model in both Go and -free — -free takes precedence."""
        registry._go_models = ["deepseek-v4-flash-free"]
        assert registry.get_tier("deepseek-v4-flash-free") == "free_ratelimited"

    # ── Quota health ──────────────────────────────────────────────

    async def test_quota_defaults_false(self, registry):
        assert registry.is_quota_exhausted() is False

    async def test_mark_quota_exhausted(self, registry):
        registry.mark_quota_exhausted()
        assert registry.is_quota_exhausted() is True

    async def test_clear_quota_exhausted(self, registry):
        registry.mark_quota_exhausted()
        registry.clear_quota_exhausted()
        assert registry.is_quota_exhausted() is False

    async def test_quota_thread_safety(self, registry):
        """Concurrent mark/clear should not race."""
        errors = []

        def hammer():
            for _ in range(100):
                try:
                    registry.mark_quota_exhausted()
                    registry.clear_quota_exhausted()
                except Exception as e:
                    errors.append(e)

        threads = [threading.Thread(target=hammer) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors

    # ── Summary ───────────────────────────────────────────────────

    async def test_summary_empty(self, registry):
        s = registry.summary()
        assert s["total_models"] == 0
        assert s["go_models"] == 0
        assert s["free_candidates"] == 0
        assert s["go_quota_exhausted"] is False
        assert s["tier_counts"] == {}

    async def test_summary_with_models(self, registry):
        registry._go_models = ["qwen3.7-max", "deepseek-v4-flash", "minimax-m3"]
        registry._free_candidates = ["deepseek-v4-flash-free"]
        registry._all_models = ["qwen3.7-max", "deepseek-v4-flash", "minimax-m3", "deepseek-v4-flash-free"]

        s = registry.summary()
        assert s["total_models"] == 4
        assert s["go_models"] == 3
        assert s["free_candidates"] == 1
        assert s["tier_counts"]["go_premium"] == 1
        assert s["tier_counts"]["go_standard"] == 1
        assert s["tier_counts"]["go_economy"] == 1
        assert s["tier_counts"]["free_ratelimited"] == 1

    # ── Thread safety ─────────────────────────────────────────────

    async def test_concurrent_read_write(self, registry):
        """Concurrent get_go_models() and refresh should not crash."""
        registry._go_models = ["a", "b", "c"]

        def writer():
            for _ in range(50):
                with registry._lock:
                    registry._go_models.append("x")
                    registry._go_models.pop()

        def reader():
            for _ in range(50):
                _ = registry.get_go_models()
                _ = registry.get_tier("a")
                _ = registry.is_quota_exhausted()

        threads = [threading.Thread(target=writer) for _ in range(3)]
        threads += [threading.Thread(target=reader) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()


# ═══════════════════════════════════════════════════════════════════
# 3. Singleton & helpers
# ═══════════════════════════════════════════════════════════════════

class TestSingleton:
    """get_model_registry and ensure_registry_refreshed."""

    def setup_method(self):
        # Clear global singleton between tests
        import src.llm.model_registry as mr
        mr._registry = None

    async def test_singleton_returns_same_instance(self):
        r1 = get_model_registry()
        r2 = get_model_registry()
        assert r1 is r2

    async def test_singleton_thread_safety(self):
        instances = set()
        lock = threading.Lock()

        def get():
            r = get_model_registry()
            with lock:
                instances.add(id(r))

        threads = [threading.Thread(target=get) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(instances) == 1

    @patch("src.llm.model_registry._registry")
    async def test_ensure_registry_refreshed_skips_if_has_models(
        self, mock_registry
    ):
        """Does not call refresh() when Go models already exist."""
        mock_registry.get_go_models.return_value = ["model-a"]
        mock_registry.refresh = AsyncMock()

        from src.llm.model_registry import ensure_registry_refreshed
        await ensure_registry_refreshed()

        mock_registry.refresh.assert_not_called()
