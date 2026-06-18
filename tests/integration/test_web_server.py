import pytest
from unittest.mock import AsyncMock
from unittest.mock import MagicMock, patch

from fastapi import BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from web.server import app
from src.api.session import ensure_session


def _request(path: str = "/", current: str = "") -> MagicMock:
    request = MagicMock()
    request.query_params.get.return_value = current
    request.url.path = path
    return request


@pytest.mark.anyio
async def test_app_is_created():
    assert app is not None
    assert any(route.path == "/" for route in app.routes)


@patch("web.routers.pages.get_available_model_ids", return_value=["m1", "m2"])
@patch("web.routers.pages.templates.TemplateResponse")
@pytest.mark.anyio
async def test_home_page(mock_tpl, _mock_models):
    mock_tpl.return_value = HTMLResponse("<html></html>")
    from web.routers.pages import home
    resp = home(_request("/"))
    assert isinstance(resp, HTMLResponse)


@patch("web.routers.pages.get_available_model_ids", return_value=["m1"])
@patch("web.routers.pages.templates.TemplateResponse")
@pytest.mark.anyio
async def test_session_page(mock_tpl, _mock_models):
    mock_tpl.return_value = HTMLResponse("<html></html>")
    from web.routers.pages import session_page
    resp = session_page(_request("/sessions/test-session-123"), "test-session-123")
    assert isinstance(resp, HTMLResponse)


@patch("web.routers.pages.get_repos")
@patch("web.routers.pages.templates.TemplateResponse")
@pytest.mark.anyio
async def test_sidebar(mock_tpl, mock_get_repos):
    mock_tpl.return_value = HTMLResponse("<div></div>")
    mock_repos = AsyncMock()
    mock_repos.sessions.get_all.return_value = []
    mock_get_repos.return_value = mock_repos
    from web.routers.pages import sidebar
    resp = await sidebar(_request("/sidebar", current="test-session-abc"))
    assert isinstance(resp, HTMLResponse)


@pytest.mark.anyio
async def test_session_messages_empty():
    from web.routers.pages import session_messages
    resp = await session_messages(_request("/sessions/test-session-abc"), "test-session-abc")
    assert isinstance(resp, dict)
    assert resp["messages"] == []


@patch("web.routers.chat.build_stream_generator")
@patch("web.routers.chat.rebuild_history", return_value=[])
@patch("web.routers.chat.get_default_model", return_value="test-model")
@pytest.mark.anyio
async def test_chat_streaming(_mock_default, _mock_history, mock_builder):
    from src.memory.schema import init_db
    from src.api.session import ensure_session
    await init_db()
    await ensure_session("test-session-abc")
    from web.routers.chat import chat

    mock_builder.return_value = lambda: iter([
        '{"t":"reasoning","d":"Thinking..."}\n',
        '{"t":"content","d":"Hello from mocked LLM"}\n',
    ])

    req = MagicMock()
    req.app.state.repos = None
    response = await chat("test-session-abc", req, BackgroundTasks(), message="hello", model="test-model")
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/x-ndjson"


@pytest.mark.anyio
async def test_rename_session():
    from src.memory.schema import init_db
    await init_db()
    from web.routers.sessions import rename
    await ensure_session("test-session-abc")

    req = MagicMock()
    req.app.state.repos = None
    response = await rename("test-session-abc", req, name="New Chat Name")
    assert isinstance(response, JSONResponse)
    assert b"ok" in response.body


@pytest.mark.anyio
async def test_delete_session():
    from src.memory.schema import init_db
    await init_db()
    from web.routers.sessions import delete
    await ensure_session("test-session-abc")

    req = MagicMock()
    req.app.state.repos = None
    response = await delete("test-session-abc", req)
    assert isinstance(response, JSONResponse)
    assert b"ok" in response.body


@pytest.mark.anyio
async def test_debug_info_empty():
    from src.memory.schema import init_db
    await init_db()
    from web.routers.debug import debug_info
    await ensure_session("test-session-abc")

    req = MagicMock()
    req.app.state.repos = None
    response = await debug_info("test-session-abc", req)
    assert isinstance(response, JSONResponse)
    assert response.body == b"{}"
