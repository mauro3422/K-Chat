import pytest
from unittest.mock import patch


def _mock_stream(response_text):
    """Build a generator that simulates orchestrator.chat_stream with tagged=False."""
    def _gen(message_user, history, **kwargs):
        if not history:
            history.append({"role": "system", "content": "sys prompt"})
        history.append({"role": "user", "content": message_user})
        history.append({"role": "assistant", "content": response_text})
        yield response_text
    return _gen


@patch("src.core.orchestrator.chat_stream")
def test_chat_basic(mock_chat_stream):
    mock_chat_stream.side_effect = _mock_stream("Hello!")
    from src.core.chat_sync import chat

    resp, history = chat("Hi", [{"role": "system", "content": "sys"}])
    assert resp == "Hello!"
    assert len(history) == 3
    assert history[1] == {"role": "user", "content": "Hi"}
    assert history[2] == {"role": "assistant", "content": "Hello!"}
    mock_chat_stream.assert_called_once()
    assert mock_chat_stream.call_args[0][0] == "Hi"
    assert mock_chat_stream.call_args[1]["streaming"] is False
    assert mock_chat_stream.call_args[1]["tagged"] is False


@patch("src.core.orchestrator.chat_stream")
def test_chat_no_history(mock_chat_stream):
    mock_chat_stream.side_effect = _mock_stream("Response")
    from src.core.chat_sync import chat

    resp, history = chat("Hi")
    assert resp == "Response"
    assert len(history) == 3
    assert history[0] == {"role": "system", "content": "sys prompt"}
    assert history[1] == {"role": "user", "content": "Hi"}
    mock_chat_stream.assert_called_once()
    assert mock_chat_stream.call_args[0][0] == "Hi"
    assert mock_chat_stream.call_args[1]["streaming"] is False
    assert mock_chat_stream.call_args[1]["tagged"] is False


@patch("src.core.orchestrator.chat_stream")
def test_chat_with_existing_history(mock_chat_stream):
    mock_chat_stream.side_effect = _mock_stream("OK")
    from src.core.chat_sync import chat

    existing = [{"role": "system", "content": "sys"}, {"role": "user", "content": "prev"}]
    resp, history = chat("next", existing)
    assert resp == "OK"
    assert len(history) == 4
    assert history[2] == {"role": "user", "content": "next"}
    assert history[3] == {"role": "assistant", "content": "OK"}
    mock_chat_stream.assert_called_once()
    assert mock_chat_stream.call_args[0][0] == "next"
    assert mock_chat_stream.call_args[1]["streaming"] is False
    assert mock_chat_stream.call_args[1]["tagged"] is False


@patch("src.core.orchestrator.chat_stream")
def test_chat_error_propagation(mock_chat_stream):
    mock_chat_stream.side_effect = RuntimeError("API error")
    from src.core.chat_sync import chat

    with pytest.raises(RuntimeError, match="API error"):
        chat("Hi", [{"role": "system", "content": "sys"}])


@patch("src.core.orchestrator.chat_stream")
def test_chat_empty_message(mock_chat_stream):
    mock_chat_stream.side_effect = _mock_stream("")
    from src.core.chat_sync import chat

    resp, history = chat("", [{"role": "system", "content": "sys"}])
    assert resp == ""
    assert history[-1]["content"] == ""
