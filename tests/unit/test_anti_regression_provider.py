"""Anti-regression tests for model_state, message sanitization, and error classifier.

Covers fixes for: ghost fallback (big-pickle), content:null 400, error classification.
"""

from __future__ import annotations

import time
import pytest


class TestModelStateTTL:
    """Verify failed models auto-recover after MODEL_FAIL_TTL seconds."""

    def test_failed_model_recovers_after_ttl(self):
        from src.llm.model_state import ModelState, MODEL_FAIL_TTL
        state = ModelState()
        state.mark_model_failed("deepseek-v4-flash")
        assert state.is_model_failed("deepseek-v4-flash") is True
        # Expire the timestamp
        state._failed_models["deepseek-v4-flash"] = time.monotonic() - MODEL_FAIL_TTL - 10
        assert state.is_model_failed("deepseek-v4-flash") is False

    def test_switch_model_skips_failed(self):
        from src.llm.model_state import ModelState
        state = ModelState(priority=["a", "b", "c"])
        state.mark_model_failed("a")
        assert state.switch_model("a") == "b"

    def test_switch_model_returns_expired(self):
        from src.llm.model_state import ModelState, MODEL_FAIL_TTL
        state = ModelState(priority=["a", "b"])
        state.mark_model_failed("a")
        state._failed_models["a"] = time.monotonic() - MODEL_FAIL_TTL - 10
        assert state.switch_model("b") == "a"

    def test_clear_failed_models(self):
        from src.llm.model_state import ModelState
        state = ModelState(priority=["a", "b"])
        state.mark_model_failed("a")
        state.clear_failed_models()
        assert not state.is_model_failed("a")

    def test_switch_model_raises_when_all_failed(self):
        from src.llm.model_state import ModelState
        state = ModelState(priority=["a", "b"])
        state.mark_model_failed("a")
        state.mark_model_failed("b")
        with pytest.raises(RuntimeError, match="All models have failed"):
            state.switch_model("a")


class TestMessageSanitization:
    """Verify _to_openai_messages preserves content:null and strips extras."""

    def test_preserves_content_null(self):
        from src.llm.adapters.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test", base_url="http://localhost")
        messages = [
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "1", "function": {"name": "test", "arguments": "{}"}}
            ], "created_at": "x", "reasoning": "", "phases": "[]", "id": 1},
        ]
        result = adapter._to_openai_messages(messages)
        assert "content" in result[0]

    def test_strips_extra_fields(self):
        from src.llm.adapters.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test", base_url="http://localhost")
        messages = [
            {"role": "user", "content": "hi", "created_at": "x", "reasoning": "y",
             "phases": "[]", "id": 42},
        ]
        result = adapter._to_openai_messages(messages)
        assert set(result[0].keys()) == {"role", "content"}

    def test_strips_null_tool_calls(self):
        from src.llm.adapters.openai_adapter import OpenAIAdapter
        adapter = OpenAIAdapter(api_key="test", base_url="http://localhost")
        messages = [{"role": "assistant", "content": "hello", "tool_calls": None}]
        result = adapter._to_openai_messages(messages)
        assert "tool_calls" not in result[0]


class TestErrorClassifier:
    """Verify classify_error returns correct types."""

    def test_bad_request(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("BadRequestError 400"))[0] == "bad_request"

    def test_credits(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("CreditsError: Insufficient balance"))[0] == "credits"

    def test_auth_401(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("AuthenticationError 401"))[0] == "auth"

    def test_rate_limit(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("Rate limit 429"))[0] == "rate_limit"

    def test_go_usage_limit(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("GoUsageLimitError: Monthly usage limit reached"))[0] == "credits"

    def test_timeout(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("Request timeout"))[0] == "timeout"

    def test_unknown(self):
        from web.services.stream_error_classifier import classify_error
        assert classify_error(Exception("random weirdness"))[0] == "unknown"
