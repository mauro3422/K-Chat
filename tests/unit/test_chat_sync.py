import pytest
from unittest.mock import patch


@patch("src.core.chat_sync.llm_chat")
@patch("src.core.chat_sync.build_system_prompt")
@patch("src.core.chat_sync.get_default_model")
def test_chat_basic(mock_get_model, mock_build_sp, mock_llm_chat, make_choice):
    mock_get_model.return_value = "test-model"
    mock_llm_chat.return_value = make_choice(content="Hello!")
    from src.core.chat_sync import chat

    resp, history = chat("Hi", [{"role": "system", "content": "sys"}])
    assert resp == "Hello!"
    assert len(history) == 3
    assert history[1] == {"role": "user", "content": "Hi"}
    assert history[2] == {"role": "assistant", "content": "Hello!"}
    mock_llm_chat.assert_called_once()
    mock_build_sp.assert_not_called()


@patch("src.core.chat_sync.llm_chat")
@patch("src.core.chat_sync.build_system_prompt")
@patch("src.core.chat_sync.get_default_model")
def test_chat_no_history(mock_get_model, mock_build_sp, mock_llm_chat, make_choice):
    mock_get_model.return_value = "test-model"
    mock_build_sp.return_value = {"role": "system", "content": "sys prompt"}
    mock_llm_chat.return_value = make_choice(content="Response")
    from src.core.chat_sync import chat

    resp, history = chat("Hi")
    assert resp == "Response"
    assert len(history) == 3
    assert history[0] == {"role": "system", "content": "sys prompt"}
    assert history[1] == {"role": "user", "content": "Hi"}
    mock_build_sp.assert_called_once_with("test-model")


@patch("src.core.chat_sync.llm_chat")
@patch("src.core.chat_sync.build_system_prompt")
@patch("src.core.chat_sync.get_default_model")
def test_chat_with_existing_history(mock_get_model, mock_build_sp, mock_llm_chat, make_choice):
    mock_get_model.return_value = "test-model"
    mock_llm_chat.return_value = make_choice(content="OK")
    from src.core.chat_sync import chat

    existing = [{"role": "system", "content": "sys"}, {"role": "user", "content": "prev"}]
    resp, history = chat("next", existing)
    assert resp == "OK"
    assert len(history) == 4
    assert history[2] == {"role": "user", "content": "next"}
    assert history[3] == {"role": "assistant", "content": "OK"}
    mock_build_sp.assert_not_called()


@patch("src.core.chat_sync.llm_chat")
@patch("src.core.chat_sync.build_system_prompt")
@patch("src.core.chat_sync.get_default_model")
def test_chat_error_propagation(mock_get_model, mock_build_sp, mock_llm_chat):
    mock_get_model.return_value = "test-model"
    mock_llm_chat.side_effect = RuntimeError("API error")
    from src.core.chat_sync import chat

    with pytest.raises(RuntimeError, match="API error"):
        chat("Hi", [{"role": "system", "content": "sys"}])


@patch("src.core.chat_sync.llm_chat")
@patch("src.core.chat_sync.build_system_prompt")
@patch("src.core.chat_sync.get_default_model")
def test_chat_empty_message(mock_get_model, mock_build_sp, mock_llm_chat, make_choice):
    mock_get_model.return_value = "test-model"
    mock_llm_chat.return_value = make_choice(content="")
    from src.core.chat_sync import chat

    resp, history = chat("", [{"role": "system", "content": "sys"}])
    assert resp == ""
    assert history[-1]["content"] == ""
