from unittest.mock import patch, MagicMock

import pytest

from src.llm.client import chat
from src.llm.model_state import clear_failed_models, set_cached_models, set_verified_models
from src.llm.api_call import _api_call
from src.context import build_system_prompt

@patch("src.llm.retry.time.sleep")
def test_fallback_switch_updates_system_prompt(mock_sleep):
    clear_failed_models()
    set_cached_models(None)
    set_verified_models(None)
    
    # Mocking choice response
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Response from fallback"
    mock_response.choices = [mock_choice]
    
    with patch("src.llm.client._mark_and_refresh") as mock_mark_and_refresh, patch("src.llm.client.api_call._api_call") as mock_api_call:
        mock_mark_and_refresh.return_value = "deepseek-v4-flash-free"
        mock_api_call.side_effect = [
            Exception("Connection error"),
            mock_response,
        ]
        
        messages = [
            {"role": "system", "content": "Original system prompt for big-pickle"},
            {"role": "user", "content": "Hello"}
        ]
        
        res = chat(messages, model="big-pickle", build_prompt_fn=build_system_prompt)

        # Verify the returned choice
        assert res.message.content == "Response from fallback"
        assert mock_api_call.call_count == 2
        assert mock_api_call.call_args_list[0].kwargs.get("model") == "big-pickle"
        assert mock_api_call.call_args_list[1].kwargs.get("model") == "deepseek-v4-flash-free"
        mock_mark_and_refresh.assert_called_once_with("big-pickle", refresh=True)
        
        # Verify system prompt was updated
        assert "Active model: deepseek-v4-flash-free" in messages[0]["content"]
        

@patch("src.llm.retry.time.sleep")
def test_api_call_retries_on_rate_limit(mock_sleep):
    class DummyRateLimitError(Exception):
        status_code = 429

    with patch("src.llm.api_call._get_provider") as mock_get_provider:
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = DummyRateLimitError("HTTP 429 Too Many Requests")
        mock_get_provider.return_value = mock_provider

        with pytest.raises(DummyRateLimitError):
            _api_call(model="big-pickle", messages=[])

        assert mock_provider.chat.call_count == 3
