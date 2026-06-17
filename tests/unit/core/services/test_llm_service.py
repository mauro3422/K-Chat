import time
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from typing import AsyncGenerator, Any

from src.core.services.llm_service import LLMService


@pytest.mark.anyio
async def test_chat_calls_injected_chat_fn():
    chat_fn = AsyncMock(return_value="response!")
    service = LLMService(chat_fn=chat_fn)

    result = await service.chat(
        [{"role": "user", "content": "hi"}],
        "gpt-4",
        temperature=0.7,
    )

    chat_fn.assert_awaited_once_with(
        [{"role": "user", "content": "hi"}],
        "gpt-4",
        temperature=0.7,
    )
    assert result == "response!"


@pytest.mark.anyio
async def test_chat_uses_default_client_when_no_fn():
    mock_chat = AsyncMock(return_value="ok")

    with patch("src.core.services.llm_service.llm_client.chat", mock_chat):
        service = LLMService()
        result = await service.chat([{"role": "user", "content": "hi"}], "gpt-4")

    assert result == "ok"


@pytest.mark.anyio
async def test_chat_tracks_telemetry_when_available():
    telemetry = MagicMock()
    chat_fn = AsyncMock()
    chat_fn.return_value = MagicMock(
        usage=MagicMock(total_tokens=42),
    )

    service = LLMService(chat_fn=chat_fn, telemetry_service=telemetry)

    await service.chat([{"role": "user", "content": "hi"}], "gpt-4")

    telemetry.track_llm_usage.assert_called_once()
    args = telemetry.track_llm_usage.call_args[0]
    assert args[0] == "gpt-4"
    assert args[1] == 42


@pytest.mark.anyio
async def test_chat_skips_telemetry_when_none():
    chat_fn = AsyncMock(return_value="response")
    service = LLMService(chat_fn=chat_fn, telemetry_service=None)

    result = await service.chat([], "gpt-4")

    assert result == "response"


@pytest.mark.anyio
async def test_chat_handles_dict_response_usage():
    telemetry = MagicMock()
    chat_fn = AsyncMock()
    chat_fn.return_value = {"usage": {"total_tokens": 99}}

    service = LLMService(chat_fn=chat_fn, telemetry_service=telemetry)
    await service.chat([], "gpt-4")

    telemetry.track_llm_usage.assert_called_once_with("gpt-4", 99, pytest.approx(0, abs=2))


@pytest.mark.anyio
async def test_chat_stream_calls_injected_stream_fn():
    async def fake_stream(messages, model, **kwargs):
        yield "chunk1"
        yield "chunk2"

    service = LLMService(chat_stream_fn=fake_stream)

    chunks: list[str] = []
    async for chunk in service.chat_stream([{"role": "user", "content": "hi"}], "gpt-4"):
        chunks.append(chunk)

    assert chunks == ["chunk1", "chunk2"]


@pytest.mark.anyio
async def test_chat_stream_uses_default_when_no_fn():
    async def default_stream(messages, model, **kwargs):
        yield "default"

    with patch(
        "src.core.services.llm_service.llm_client.chat_stream",
        return_value=default_stream([], ""),
    ):
        service = LLMService()
        chunks: list[str] = []
        async for chunk in service.chat_stream([], "gpt-4"):
            chunks.append(chunk)

    assert chunks == ["default"]


@pytest.mark.anyio
async def test_chat_stream_tracks_telemetry():
    telemetry = MagicMock()

    async def fake_stream(messages, model, **kwargs):
        yield "chunk"

    service = LLMService(chat_stream_fn=fake_stream, telemetry_service=telemetry)

    async for _ in service.chat_stream([], "gpt-4"):
        pass

    telemetry.track_llm_usage.assert_called_once()
    args = telemetry.track_llm_usage.call_args[0]
    assert args[0] == "gpt-4"


@pytest.mark.anyio
async def test_get_default_model_uses_injected_fn():
    service = LLMService(default_model_fn=lambda: "custom-model")
    assert service.get_default_model() == "custom-model"


@pytest.mark.anyio
async def test_get_default_model_falls_back():
    with patch(
        "src.core.services.llm_service.get_default_model",
        return_value="fallback-model",
    ):
        service = LLMService()
        assert service.get_default_model() == "fallback-model"
