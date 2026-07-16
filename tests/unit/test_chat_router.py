import json

import pytest
from unittest.mock import ANY, patch, AsyncMock, MagicMock

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from web.routers.chat import router, chat, ChatPayload
from web.services.session_stream_locks import SessionStreamLockManager
from src.core.debug_info import DebugInfo


@pytest.mark.anyio
async def test_router_exists():
    """Module exports an APIRouter instance."""
    assert isinstance(router, APIRouter)


@pytest.mark.anyio
async def test_router_has_routes():
    """Router should have at least one route registered."""
    assert len(router.routes) >= 1
    route_paths = [r.path for r in router.routes]
    assert "/chat/{session_id}" in route_paths


@pytest.mark.anyio
async def test_chat_empty_message():
    """Empty message should return an empty string Response."""
    bt = BackgroundTasks()
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        await chat("s1", request, bt, message="   ", model="m1", files=[])
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_chat_empty_session_id():
    """Empty or whitespace-only session_id should raise 400."""
    bt = BackgroundTasks()
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        await chat("", request, bt, message="hello", model="m1", files=[])
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await chat("   ", request, bt, message="hello", model="m1", files=[])
    assert exc.value.status_code == 400


def _make_mock_repos():
    repos = MagicMock()
    repos.sessions.ensure = AsyncMock()
    repos.messages.save_record = AsyncMock()
    return repos


def _make_request():
    request = MagicMock()
    request.app.state = MagicMock(
        repos=None,
        history_service=MagicMock(),
        telemetry_service=MagicMock(),
        llm_service=MagicMock(),
        tool_service=MagicMock(),
        retrieval_service=MagicMock(),
        logbus=None,
    )
    return request


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.get_repos")
@patch("web.routers.chat.rebuild_history", new_callable=AsyncMock)
@patch("web.routers.chat.build_stream_generator")
@pytest.mark.anyio
async def test_chat_success(mock_build_gen, mock_rebuild, mock_get_repos, mock_default):
    """Chat with valid inputs returns a StreamingResponse and delegates correctly."""
    mock_rebuild.return_value = [{"role": "user", "content": "hello"}]
    mock_get_repos.return_value = _make_mock_repos()
    request = _make_request()

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", request, bt, message="hello", model="my-model", files=[])

    assert isinstance(result, StreamingResponse)
    assert result.media_type == "application/x-ndjson"

    mock_get_repos.return_value.sessions.ensure.assert_called_once_with("s1", origin_node_id=ANY)
    mock_rebuild.assert_called_once()
    args, kwargs = mock_rebuild.call_args
    assert args[0] == "s1"
    assert args[1] == "my-model"
    mock_get_repos.return_value.messages.save_record.assert_called_once()
    save_record = mock_get_repos.return_value.messages.save_record.call_args[0][0]
    assert save_record.session_id == "s1"
    assert save_record.role == "user"
    assert save_record.content == "hello"
    assert save_record.model == "my-model"
    mock_default.assert_not_called()  # model was provided


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.get_repos")
@patch("web.routers.chat.rebuild_history", new_callable=AsyncMock)
@patch("web.routers.chat.build_stream_generator")
@pytest.mark.anyio
async def test_chat_uses_query_model(mock_build_gen, mock_rebuild, mock_get_repos, mock_default):
    """Querystring model should override the default model."""
    mock_rebuild.return_value = [{"role": "user", "content": "hello"}]
    mock_get_repos.return_value = _make_mock_repos()
    request = _make_request()

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", request, bt, message="hello", model="query-model", files=[])

    assert isinstance(result, StreamingResponse)
    mock_rebuild.assert_called_once()
    args, kwargs = mock_rebuild.call_args
    assert args[0] == "s1"
    assert args[1] == "query-model"
    mock_get_repos.return_value.messages.save_record.assert_called_once()
    save_record = mock_get_repos.return_value.messages.save_record.call_args[0][0]
    assert save_record.session_id == "s1"
    assert save_record.role == "user"
    assert save_record.content == "hello"
    assert save_record.model == "query-model"
    mock_default.assert_not_called()


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.get_repos")
@patch("web.routers.chat.rebuild_history", new_callable=AsyncMock)
@patch("web.routers.chat.build_stream_generator")
@pytest.mark.anyio
async def test_chat_uses_default_model(mock_build_gen, mock_rebuild, mock_get_repos, mock_default):
    """When model is empty, get_default_model is called."""
    mock_rebuild.return_value = [{"role": "user", "content": "hello"}]
    mock_get_repos.return_value = _make_mock_repos()
    request = _make_request()

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", request, bt, message="hello", model=None, files=[])

    assert isinstance(result, StreamingResponse)
    mock_default.assert_called_once()
    mock_rebuild.assert_called_once()
    args, kwargs = mock_rebuild.call_args
    assert args[0] == "s1"
    assert args[1] == "fallback-model"


@patch("web.routers.chat.rebuild_history", side_effect=Exception("DB fail"))
@patch("web.routers.chat.get_repos")
@pytest.mark.anyio
async def test_chat_rebuild_history_error(mock_get_repos, mock_rebuild):
    """If rebuild_history raises, chat returns 500."""
    mock_get_repos.return_value = _make_mock_repos()
    bt = BackgroundTasks()
    request = _make_request()
    with pytest.raises(HTTPException) as exc:
        await chat("s1", request, bt, message="hello", model="m1", files=[])
    assert exc.value.status_code == 500
    assert "Error loading history" in exc.value.detail


@patch("web.services.message_persister.log_turn")
@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.get_repos")
@patch("web.routers.chat.rebuild_history", new_callable=AsyncMock)
@patch("web.routers.chat.build_stream_generator")
@pytest.mark.anyio
async def test_chat_save_wrapper_journals_once(mock_build_gen, mock_rebuild, mock_get_repos, mock_default, mock_log_turn):
    """The router wrapper must not journal a second time."""
    repos = _make_mock_repos()
    repos.debug.save_info = AsyncMock()
    mock_get_repos.return_value = repos
    mock_rebuild.return_value = [{"role": "user", "content": "hello"}]
    request = _make_request()

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'

    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    await chat("s1", request, bt, message="hello", model="my-model", files=[])

    save_fn = mock_build_gen.call_args.kwargs["deps"].save_fn
    await save_fn(
        session_id="s1",
        user_msg="hello",
        full_content="assistant text",
        full_reasoning="",
        phases_output=[],
        debug_info=DebugInfo(),
        model="my-model",
    )

    assert mock_log_turn.call_count == 1
    assert mock_log_turn.call_args.kwargs["user_msg"] == "hello"


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.get_repos")
@patch("web.routers.chat.rebuild_history", new_callable=AsyncMock)
@patch("web.routers.chat.build_stream_generator")
@pytest.mark.anyio
async def test_chat_rejects_second_stream_for_same_session(mock_build_gen, mock_rebuild, mock_get_repos, mock_default):
    """A concurrent request for the same session should return a busy error stream."""
    mock_rebuild.return_value = [{"role": "user", "content": "hello"}]
    mock_get_repos.return_value = _make_mock_repos()
    request = _make_request()
    manager = SessionStreamLockManager()
    request.app.state.chat_stream_lock_manager = manager

    held = await manager.try_acquire("s1")
    assert held is not None

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'

    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", request, bt, message="hello", model="my-model", files=[])
    chunks = []
    async for chunk in result.body_iterator:
        chunks.append(chunk.decode() if isinstance(chunk, bytes) else chunk)

    payload = json.loads("".join(chunks))
    assert payload == {
        "t": "error",
        "d": {
            "type": "bad_request",
            "message": "Ya hay un stream activo para esta sesión",
        },
    }
    mock_build_gen.assert_not_called()
    manager.release("s1", held)
