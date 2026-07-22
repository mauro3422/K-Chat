import pytest
from unittest.mock import AsyncMock
from web.services.stream_retry_handler import (
    StreamRetryHandler,
    build_continuation_instruction,
)


@pytest.mark.anyio
async def test_can_retry_starts_true():
    h = StreamRetryHandler(max_retries=2)
    assert h.can_retry is True
    assert h.retry_count == 0


@pytest.mark.anyio
async def test_can_retry_false_after_exhaustion():
    h = StreamRetryHandler(max_retries=1)
    h.retry_count = 1
    assert h.can_retry is False


@pytest.mark.anyio
async def test_zero_max_retries():
    h = StreamRetryHandler(max_retries=0)
    assert h.can_retry is False


@pytest.mark.anyio
async def test_build_messages_adds_partial_assistant():
    h = StreamRetryHandler()
    history = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Write a poem."},
    ]
    messages = h.build_messages(history, partial_content="Roses are red",
                                 partial_reasoning="")

    assert len(messages) == 3
    assert messages[0] == history[0]
    assert messages[1] == history[1]
    assert messages[2]["role"] == "assistant"
    assert "Roses are red" in messages[2]["content"]


@pytest.mark.anyio
async def test_build_messages_combines_reasoning_and_content():
    h = StreamRetryHandler()
    history = [{"role": "user", "content": "Explain."}]
    messages = h.build_messages(history,
                                 partial_content="Final answer.",
                                 partial_reasoning="Thinking step 1")

    assert len(messages) == 2
    asst_msg = messages[1]
    assert asst_msg["role"] == "assistant"
    assert asst_msg["reasoning_content"] == "Thinking step 1"
    assert asst_msg["content"] == "Final answer."


@pytest.mark.anyio
async def test_continuation_instruction_reports_error_and_allows_tools():
    instruction = build_continuation_instruction("network", "connection lost")
    assert "network" in instruction
    assert "connection lost" in instruction
    assert "may use tools" in instruction


@pytest.mark.anyio
async def test_attempt_recovery_returns_empty_when_exhausted():
    """When max_retries=0, attempt_recovery yields nothing."""
    h = StreamRetryHandler(max_retries=0)
    gen = h.attempt_recovery([], "hi", "", "gpt-4")
    items = [item async for item in gen]
    assert items == []


class TestAttemptRecovery:
    @pytest.mark.anyio
    async def test_cannot_retry_when_exhausted(self):
        handler = StreamRetryHandler(max_retries=0)
        assert not handler.can_retry

    @pytest.mark.anyio
    async def test_attempt_recovery_yields_nothing_on_exhausted(self):
        handler = StreamRetryHandler(max_retries=1)
        handler.retry_count = 1  # simulate exhausted
        gen = handler.attempt_recovery([], "", "", "model")
        result = [item async for item in gen]
        assert result == []  # yields nothing when exhausted
