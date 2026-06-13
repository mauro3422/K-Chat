import pytest
from unittest.mock import ANY, patch

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from web.routers.chat import router, chat, ChatPayload


def test_router_exists():
    """Module exports an APIRouter instance."""
    assert isinstance(router, APIRouter)


def test_router_has_routes():
    """Router should have at least one route registered."""
    assert len(router.routes) >= 1
    route_paths = [r.path for r in router.routes]
    assert "/chat/{session_id}" in route_paths


def test_chat_empty_message():
    """Empty message should return an empty string Response."""
    bt = BackgroundTasks()
    result = chat("s1", bt, ChatPayload(message="   ", model="m1"))
    assert result == ""


def test_chat_empty_session_id():
    """Empty or whitespace-only session_id should raise 400."""
    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        chat("", bt, ChatPayload(message="hello", model="m1"))
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        chat("   ", bt, ChatPayload(message="hello", model="m1"))
    assert exc.value.status_code == 400


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.ensure_session")
@patch("web.routers.chat.rebuild_history", return_value=[{"role": "user", "content": "hello"}])
@patch("web.routers.chat.db_save_message")
@patch("web.routers.chat.build_stream_generator")
def test_chat_success(mock_build_gen, mock_save, mock_rebuild, mock_ensure, mock_default):
    """Chat with valid inputs returns a StreamingResponse and delegates correctly."""
    def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = chat("s1", bt, ChatPayload(message="hello", model="my-model"))

    assert isinstance(result, StreamingResponse)
    assert result.media_type == "application/x-ndjson"

    mock_ensure.assert_called_once_with("s1")
    mock_rebuild.assert_called_once_with("s1", "my-model", ANY)
    mock_save.assert_called_once_with("s1", "user", "hello", "my-model")
    mock_default.assert_not_called()  # model was provided


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.ensure_session")
@patch("web.routers.chat.rebuild_history", return_value=[{"role": "user", "content": "hello"}])
@patch("web.routers.chat.db_save_message")
@patch("web.routers.chat.build_stream_generator")
def test_chat_uses_query_model(mock_build_gen, mock_save, mock_rebuild, mock_ensure, mock_default):
    """Querystring model should override the default model."""
    def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = chat("s1", bt, ChatPayload(message="hello", model=None), model="query-model")

    assert isinstance(result, StreamingResponse)
    mock_rebuild.assert_called_once_with("s1", "query-model", ANY)
    mock_save.assert_called_once_with("s1", "user", "hello", "query-model")
    mock_default.assert_not_called()


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.ensure_session")
@patch("web.routers.chat.rebuild_history", return_value=[{"role": "user", "content": "hello"}])
@patch("web.routers.chat.db_save_message")
@patch("web.routers.chat.build_stream_generator")
def test_chat_uses_default_model(mock_build_gen, mock_save, mock_rebuild, mock_ensure, mock_default):
    """When model is empty, get_default_model is called."""
    def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = chat("s1", bt, ChatPayload(message="hello", model=""))

    assert isinstance(result, StreamingResponse)
    mock_default.assert_called_once()
    mock_rebuild.assert_called_once_with("s1", "fallback-model", ANY)


@patch("web.routers.chat.rebuild_history", side_effect=Exception("DB fail"))
@patch("web.routers.chat.ensure_session")
def test_chat_rebuild_history_error(mock_ensure, mock_rebuild):
    """If rebuild_history raises, chat returns 500."""
    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        chat("s1", bt, ChatPayload(message="hello", model="m1"))
    assert exc.value.status_code == 500
    assert "Error loading history" in exc.value.detail
