from unittest.mock import patch, MagicMock

import pytest

from src.llm.api_call import _api_call


@patch("src.llm.api_call._get_provider")
@patch("src.llm.api_call.execute_with_retry")
def test_api_call_calls_provider_chat_with_correct_args(
    mock_execute_with_retry, mock_get_provider
):
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_provider.chat.return_value = mock_response
    mock_get_provider.return_value = mock_provider

    mock_execute_with_retry.side_effect = lambda fn, *a, **kw: fn()

    _api_call(model="test-model", messages=[{"role": "user", "content": "hello"}])

    mock_provider.chat.assert_called_once_with(
        model="test-model", messages=[{"role": "user", "content": "hello"}]
    )
    mock_execute_with_retry.assert_called_once()


@patch("src.llm.api_call._get_provider")
@patch("src.llm.api_call.execute_with_retry")
def test_api_call_uses_retry_via_execute_with_retry(
    mock_execute_with_retry, mock_get_provider
):
    mock_provider = MagicMock()
    mock_response = MagicMock()
    mock_provider.chat.return_value = mock_response
    mock_get_provider.return_value = mock_provider

    _api_call(model="test-model", messages=[])

    mock_execute_with_retry.assert_called_once()


def test_api_call_keeps_model_state_defaults():
    from src.llm.model_state import PRIORITY, FALLBACK_MODEL

    assert PRIORITY == ["deepseek-v4-flash-free", "big-pickle"]
    assert FALLBACK_MODEL == "deepseek-v4-flash-free"
