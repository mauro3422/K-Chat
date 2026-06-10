from unittest.mock import patch, MagicMock


from src.llm import chat
from src.llm.models import _failed_models
from src.context import build_system_prompt

def test_fallback_switch_updates_system_prompt():
    _failed_models.clear()
    
    # Mocking choice response
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Response from fallback"
    mock_response.choices = [mock_choice]
    
    # Mocking provider models list
    mock_model_1 = MagicMock()
    mock_model_1.id = "big-pickle"
    mock_model_2 = MagicMock()
    mock_model_2.id = "deepseek-v4-flash-free"
    
    with patch("src.llm.models._get_provider") as mock_get_provider:
        mock_provider = MagicMock()
        mock_provider.chat.side_effect = [
            Exception("Connection error"),
            mock_response,
            mock_response,
        ]
        mock_provider.list_models.return_value = [mock_model_1, mock_model_2]
        mock_get_provider.return_value = mock_provider
        
        messages = [
            {"role": "system", "content": "Original system prompt for big-pickle"},
            {"role": "user", "content": "Hello"}
        ]
        
        res = chat(messages, model="big-pickle", build_prompt_fn=build_system_prompt)
        
        # Verify the returned choice
        assert res.message.content == "Response from fallback"
        
        # call 1: big-pickle fails, call 2: verify_model(deepseek), call 3: fallback
        assert mock_provider.chat.call_count == 3
        assert mock_provider.chat.call_args_list[0].kwargs.get("model") == "big-pickle"
        assert mock_provider.chat.call_args_list[2].kwargs.get("model") == "deepseek-v4-flash-free"
        
        # Verify system prompt was updated
        assert "Active model: deepseek-v4-flash-free" in messages[0]["content"]
        
        # Verify it was added to failed models
        assert "big-pickle" in _failed_models
        
        # Now a subsequent call should automatically bypass big-pickle
        mock_provider.chat.reset_mock()
        mock_provider.chat.side_effect = [mock_response]
        
        messages2 = [
            {"role": "system", "content": "Original system prompt for big-pickle"},
            {"role": "user", "content": "Hello again"}
        ]
        res2 = chat(messages2, model="big-pickle", build_prompt_fn=build_system_prompt)
        assert res2.message.content == "Response from fallback"
        # Since big-pickle already failed, it should only call create once (directly to fallback)
        mock_provider.chat.assert_called_once()
        assert mock_provider.chat.call_args.kwargs.get("model") == "deepseek-v4-flash-free"
        assert "Active model: deepseek-v4-flash-free" in messages2[0]["content"]
