from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

import pytest

from src.llm.api_call import _api_call


@patch("src.llm.api_call.execute_with_retry")
@pytest.mark.anyio
async def test_api_call_calls_provider_chat_with_correct_args(
    mock_execute_with_retry,
):
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_provider.chat.return_value = mock_response

    async def fake_retry(fn, *a, **kw):
        return fn()
    mock_execute_with_retry.side_effect = fake_retry

    from src.llm.protocol import UnifiedRequest

    await _api_call(
        provider_fn=lambda: mock_provider,
        model="test-model",
        messages=[{"role": "user", "content": "hello"}],
    )

    mock_provider.chat.assert_called_once_with(
        UnifiedRequest(
            messages=[{"role": "user", "content": "hello"}],
            model="test-model",
            max_tokens=32768,
        )
    )

    mock_execute_with_retry.assert_called_once()


@patch("src.llm.api_call.execute_with_retry")
@pytest.mark.anyio
async def test_api_call_uses_retry_via_execute_with_retry(
    mock_execute_with_retry,
):
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_provider.chat.return_value = mock_response

    await _api_call(provider_fn=lambda: mock_provider, model="test-model", messages=[])

    mock_execute_with_retry.assert_called_once()


@pytest.mark.anyio
async def test_api_call_keeps_model_state_defaults():
    from src.llm.model_state import PRIORITY, FALLBACK_MODEL

    assert PRIORITY == ["deepseek-v4-flash", "big-pickle"]
    assert FALLBACK_MODEL == "deepseek-v4-flash"
