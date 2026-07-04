import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock, patch

from src.compressor import (
    should_compress,
    compress_history,
    MAX_HISTORY,
    KEEP_RECENT,
)


def make_msg(role="user", content="hello"):
    return {"role": role, "content": content}


class TestShouldCompress:

    @pytest.mark.anyio
    async def test_empty_history(self):
        assert should_compress([]) is False

    @pytest.mark.anyio
    async def test_under_max_history_and_under_token_limit(self):
        history = [make_msg(content="short") for _ in range(MAX_HISTORY - 1)]
        assert should_compress(history) is False

    @pytest.mark.anyio
    async def test_over_max_history_even_with_few_tokens(self):
        history = [make_msg(content="a") for _ in range(MAX_HISTORY + 5)]
        assert should_compress(history) is True

    @pytest.mark.anyio
    async def test_under_max_history_but_over_token_limit(self):
        chars_per_msg = 1000
        count = 25
        history = [make_msg(content="x" * chars_per_msg) for _ in range(count)]
        assert len(history) < MAX_HISTORY
        assert should_compress(history) is True

    @pytest.mark.anyio
    async def test_exactly_at_max_history_boundary(self):
        history = [make_msg() for _ in range(MAX_HISTORY + 1)]
        assert len(history) == MAX_HISTORY + 1
        assert should_compress(history) is True


class TestCompressHistory:

    @pytest.mark.anyio
    async def test_nothing_to_compress(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg() for _ in range(KEEP_RECENT)]
        original = list(history)

        await compress_history(history, "test-model")

        assert history == original

    @pytest.mark.anyio
    async def test_compression_with_llm(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg(content=f"msg {i}") for i in range(20)]
        recent = history[-KEEP_RECENT:]
        system = history[0]

        mock_response = MagicMock()
        mock_response.message.content = "Test summary"
        mock_llm = AsyncMock(return_value=mock_response)
        await compress_history(history, "test-model", chat_fn=mock_llm)

        mock_llm.assert_called_once()
        assert len(history) == 1 + 1 + KEEP_RECENT
        assert history[0] == system
        assert history[1] == {"role": "system", "content": "[Resumen: Test summary]"}
        assert history[2:] == recent

    @pytest.mark.anyio
    async def test_llm_exception(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg(content=f"msg {i}") for i in range(20)]
        original = list(history)

        mock_llm = AsyncMock(side_effect=RuntimeError("LLM error"))
        await compress_history(history, "test-model", chat_fn=mock_llm)

        assert history == original

    @pytest.mark.anyio
    async def test_empty_summary_from_llm(self):
        history = [{"role": "system", "content": "You are a bot."}]
        history += [make_msg(content=f"msg {i}") for i in range(20)]
        original = list(history)

        mock_response = MagicMock()
        mock_response.message.content = None
        mock_llm = AsyncMock(return_value=mock_response)
        await compress_history(history, "test-model", chat_fn=mock_llm)

        assert history == original

    @pytest.mark.anyio
    async def test_preserves_tool_pairing_at_slice_boundary(self):
        """Compressor must not orphan tool messages when slice cuts near them."""
        history = [{"role": "system", "content": "You are a bot."}]
        # Fill with enough messages to trigger compression
        history += [make_msg(content=f"old {i}") for i in range(25)]

        # Add tool chain at the end (last KEEP_RECENT messages)
        tool_call_id = "call_test_123"
        history.append({"role": "assistant", "content": None, "tool_calls": [
            {"id": tool_call_id, "type": "function", "function": {"name": "test", "arguments": "{}"}}
        ]})
        history.append({"role": "tool", "content": "result", "tool_call_id": tool_call_id})

        mock_response = MagicMock()
        mock_response.message.content = "Test summary"
        mock_llm = AsyncMock(return_value=mock_response)
        await compress_history(history, "test-model", chat_fn=mock_llm)

        # Tool messages must still have their assistant
        tool_count = sum(1 for m in history if m.get("role") == "tool")
        assert tool_count == 1, f"Tool messages should be 1, got {tool_count}"
        # Verify the assistant with tool_calls is still present
        has_assistant_with_tc = any(
            m.get("role") == "assistant" and m.get("tool_calls")
            for m in history
        )
        assert has_assistant_with_tc, "Assistant with tool_calls must be preserved"
