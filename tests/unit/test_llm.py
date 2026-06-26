from unittest.mock import ANY, patch, MagicMock, AsyncMock
from types import SimpleNamespace

import pytest

from src.llm.client import chat
from src.llm.model_state import clear_failed_models, set_cached_models
from src.llm.model_registry import set_verified_models
from src.llm.api_call import _api_call
from src.context import build_system_prompt

@pytest.mark.anyio
@patch("src.llm.retry.asyncio.sleep", new_callable=AsyncMock)
async def test_fallback_switch_updates_system_prompt(mock_sleep):
    clear_failed_models()
    set_cached_models(None)
    set_verified_models(None)
    
    # Mocking choice response
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Response from fallback"
    mock_response.choices = [mock_choice]
    
    with patch("src.llm.client._mark_and_refresh") as mock_mark_and_refresh, patch("src.llm.client.api_call._api_call", new_callable=AsyncMock) as mock_api_call:
        mock_mark_and_refresh.return_value = "deepseek-v4-flash-free"
        mock_api_call.side_effect = [
            Exception("Connection error"),
            mock_response,
        ]
        
        messages = [
            {"role": "system", "content": "Original system prompt for big-pickle"},
            {"role": "user", "content": "Hello"}
        ]
        
        res = await chat(messages, model="big-pickle", build_prompt_fn=build_system_prompt)

        # Verify the returned choice
        assert res.message.content == "Response from fallback"
        assert mock_api_call.call_count == 2
        assert mock_api_call.call_args_list[0].kwargs.get("model") == "big-pickle"
        assert mock_api_call.call_args_list[1].kwargs.get("model") == "deepseek-v4-flash-free"
        mock_mark_and_refresh.assert_called_once_with("big-pickle", refresh=True, error=ANY, breaker=None, rate_store=None, registry=None)
        
        # Verify system prompt was updated
        assert "Active model: deepseek-v4-flash-free" in messages[0]["content"]
        

@pytest.mark.anyio
@patch("src.llm.api_call.execute_with_retry")
@patch("src.llm.retry.asyncio.sleep", new_callable=AsyncMock)
async def test_api_call_retries_on_rate_limit(mock_sleep, mock_execute_with_retry):
    class DummyRateLimitError(Exception):
        status_code = 429

    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(side_effect=DummyRateLimitError("HTTP 429 Too Many Requests"))

    async def fake_retry(fn, *args, **kwargs):
        last_err = None
        for _ in range(3):
            try:
                return await fn()
            except Exception as err:
                last_err = err
        raise last_err

    mock_execute_with_retry.side_effect = fake_retry

    with pytest.raises(DummyRateLimitError):
        await _api_call(provider_fn=lambda: mock_provider, model="big-pickle", messages=[])

    assert mock_provider.chat.call_count == 3


@pytest.mark.anyio
@patch("src.llm.api_call.execute_with_retry")
async def test_free_model_uses_zen_provider_even_in_go_mode(mock_execute_with_retry):
    created_configs = []
    mock_provider = MagicMock()
    mock_provider.chat = AsyncMock(return_value=MagicMock())

    async def fake_retry(fn, *args, **kwargs):
        return await fn()

    def fake_create_provider(config=None):
        created_configs.append(config)
        return mock_provider

    cfg = SimpleNamespace(llm_mode="go")
    mock_execute_with_retry.side_effect = fake_retry

    with patch("src._config.resolve_config", return_value=cfg), patch(
        "src.llm.providers.create_provider", side_effect=fake_create_provider
    ):
        await _api_call(model="deepseek-v4-flash-free", messages=[])

    assert created_configs[0].llm_mode == "zen"
    mock_provider.chat.assert_awaited_once()
