from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

import pytest

from src.llm.verifier import verify_model


@patch("src.llm.verifier.api_call")
@pytest.mark.anyio
async def test_verify_model_returns_true_when_model_responds(mock_api_call):
    mock_api_call._api_call = AsyncMock(return_value=MagicMock())

    result = await verify_model("test-model")

    assert result is True
    mock_api_call._api_call.assert_called_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=2,
        timeout=2.0,
    )


@patch("src.llm.verifier.api_call")
@pytest.mark.anyio
async def test_verify_model_returns_false_on_api_error(mock_api_call):
    mock_api_call._api_call = AsyncMock(side_effect=Exception("API error"))

    result = await verify_model("test-model")

    assert result is False
    mock_api_call._api_call.assert_called_once_with(
        model="test-model",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=2,
        timeout=2.0,
    )


@patch("src.llm.verifier.api_call")
@pytest.mark.anyio
async def test_verify_model_uses_api_call_with_minimal_params(mock_api_call):
    mock_api_call._api_call = AsyncMock(return_value=MagicMock())

    await verify_model("test-model")

    call_kwargs = mock_api_call._api_call.call_args[1]
    assert "model" in call_kwargs
    assert "messages" in call_kwargs
    assert "max_tokens" in call_kwargs
    assert "timeout" in call_kwargs
    assert call_kwargs["max_tokens"] == 2
    assert call_kwargs["timeout"] == 2.0
