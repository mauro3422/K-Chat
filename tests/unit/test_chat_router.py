import pytest
from unittest.mock import ANY, patch, AsyncMock, MagicMock

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from web.routers.chat import router, chat, ChatPayload


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
    with pytest.raises(HTTPException) as exc:
        await chat("s1", bt, message="   ", model="m1", files=[])
    assert exc.value.status_code == 400


@pytest.mark.anyio
async def test_chat_empty_session_id():
    """Empty or whitespace-only session_id should raise 400."""
    bt = BackgroundTasks()
    with pytest.raises(HTTPException) as exc:
        await chat("", bt, message="hello", model="m1", files=[])
    assert exc.value.status_code == 400
    with pytest.raises(HTTPException) as exc:
        await chat("   ", bt, message="hello", model="m1", files=[])
    assert exc.value.status_code == 400


def _make_mock_repos():
    repos = MagicMock()
    repos.sessions.ensure = AsyncMock()
    repos.messages.save_record = AsyncMock()
    return repos


@patch("web.routers.chat.get_default_model", return_value="fallback-model")
@patch("web.routers.chat.get_repos")
@patch("web.routers.chat.rebuild_history", new_callable=AsyncMock)
@patch("web.routers.chat.build_stream_generator")
@pytest.mark.anyio
async def test_chat_success(mock_build_gen, mock_rebuild, mock_get_repos, mock_default):
    """Chat with valid inputs returns a StreamingResponse and delegates correctly."""
    mock_rebuild.return_value = [{"role": "user", "content": "hello"}]
    mock_get_repos.return_value = _make_mock_repos()

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", bt, message="hello", model="my-model", files=[])

    assert isinstance(result, StreamingResponse)
    assert result.media_type == "application/x-ndjson"

    mock_get_repos.return_value.sessions.ensure.assert_called_once_with("s1")
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

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", bt, message="hello", model="query-model", files=[])

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

    async def fake_gen():
        yield '{"t":"content","d":"hi"}\n'
    mock_build_gen.return_value = fake_gen

    bt = BackgroundTasks()
    result = await chat("s1", bt, message="hello", model=None, files=[])

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
    with pytest.raises(HTTPException) as exc:
        await chat("s1", bt, message="hello", model="m1", files=[])
    assert exc.value.status_code == 500
    assert "Error loading history" in exc.value.detail
