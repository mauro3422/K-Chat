from unittest.mock import AsyncMock
"""Tests for ModelState class - switch_model logic."""
import pytest
from src.llm.model_state import ModelState


class TestModelStateSwitchModel:
    @pytest.mark.anyio
    async def test_switch_when_fallback_available(self):
        ms = ModelState(priority=["a", "b"], fallback_model="a")
        ms.mark_model_failed("a")
        result = ms.switch_model("a")
        assert result == "b"

    @pytest.mark.anyio
    async def test_switch_when_all_failed_raises(self):
        ms = ModelState(priority=["a", "b"], fallback_model="a")
        ms.mark_model_failed("a")
        ms.mark_model_failed("b")
        with pytest.raises(RuntimeError, match="All models have failed"):
            ms.switch_model("a")

    @pytest.mark.anyio
    async def test_switch_non_fallback_model_returns_fallback(self):
        ms = ModelState(priority=["a", "b"], fallback_model="a")
        result = ms.switch_model("b")  # b is in priority, not fallback
        assert result == "a"  # fallback is available

    @pytest.mark.anyio
    async def test_switch_non_priority_model_scans_priority(self):
        ms = ModelState(priority=["a", "b"], fallback_model="a")
        result = ms.switch_model("unknown")
        assert result == "a"  # scans priority, finds 'a'

    @pytest.mark.anyio
    async def test_clear_failed_models(self):
        ms = ModelState()
        ms.mark_model_failed("test")
        assert ms.is_model_failed("test")
        ms.clear_failed_models()
        assert not ms.is_model_failed("test")

    @pytest.mark.anyio
    async def test_priority_copy(self):
        ms = ModelState(priority=["a", "b"])
        prio = ms.priority
        prio.append("c")
        assert ms.priority == ["a", "b"]  # original unchanged
