import os, sys
from unittest.mock import patch, MagicMock
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.llm import chat, chat_stream, get_default_model, _failed_models

def test_fallback_switch_updates_system_prompt():
    _failed_models.clear()
    
    # Mocking choice response
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Response from fallback"
    mock_response.choices = [mock_choice]
    
    # Mocking client models list
    mock_model_1 = MagicMock()
    mock_model_1.id = "big-pickle"
    mock_model_2 = MagicMock()
    mock_model_2.id = "deepseek-v4-flash-free"
    
    with patch("src.llm.client") as mock_client:
        mock_client.models.list.return_value = [mock_model_1, mock_model_2]
        
        # side_effect: big-pickle fails, verify_model for deepseek, fallback succeeds
        mock_client.chat.completions.create.side_effect = [
            Exception("Connection error"),  # _api_call(model="big-pickle")
            mock_response,                  # verify_model("deepseek-v4-flash-free")
            mock_response,                  # _api_call(model="deepseek-v4-flash-free") fallback
        ]
        
        messages = [
            {"role": "system", "content": "Original system prompt for big-pickle"},
            {"role": "user", "content": "Hello"}
        ]
        
        res = chat(messages, model="big-pickle")
        
        # Verify the returned choice
        assert res.message.content == "Response from fallback"
        
        # call 1: big-pickle fails, call 2: verify_model(deepseek), call 3: fallback
        assert mock_client.chat.completions.create.call_count == 3
        assert mock_client.chat.completions.create.call_args_list[0].kwargs["model"] == "big-pickle"
        assert mock_client.chat.completions.create.call_args_list[2].kwargs["model"] == "deepseek-v4-flash-free"
        
        # Verify system prompt was updated
        assert "Model: deepseek-v4-flash-free" in messages[0]["content"]
        
        # Verify it was added to failed models
        assert "big-pickle" in _failed_models
        
        # Now a subsequent call should automatically bypass big-pickle
        mock_client.chat.completions.create.reset_mock()
        mock_client.chat.completions.create.side_effect = [mock_response]
        
        messages2 = [
            {"role": "system", "content": "Original system prompt for big-pickle"},
            {"role": "user", "content": "Hello again"}
        ]
        res2 = chat(messages2, model="big-pickle")
        assert res2.message.content == "Response from fallback"
        # Since big-pickle already failed, it should only call create once (directly to fallback)
        mock_client.chat.completions.create.assert_called_once()
        assert mock_client.chat.completions.create.call_args.kwargs["model"] == "deepseek-v4-flash-free"
        assert "Model: deepseek-v4-flash-free" in messages2[0]["content"]
