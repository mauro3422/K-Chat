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


@patch("web.routers.pages.get_sessions", return_value=[])
@patch("web.routers.pages.templates.TemplateResponse")
@pytest.mark.anyio
async def test_sidebar(mock_tpl, _mock_sessions):
    mock_tpl.return_value = HTMLResponse("<div></div>")
    from web.routers.pages import sidebar
    resp = await sidebar(_request("/sidebar", current="test-session-abc"))
    assert isinstance(resp, HTMLResponse)


@pytest.mark.anyio
async def test_session_messages_empty():
    from web.routers.pages import session_messages
    resp = await session_messages("test-session-abc")
    assert isinstance(resp, dict)
    assert resp["messages"] == []


@patch("web.routers.chat.build_stream_generator")
@patch("web.routers.chat.db_save_message")
@patch("web.routers.chat.rebuild_history", return_value=[])
@patch("web.routers.chat.ensure_session")
@patch("web.routers.chat.get_default_model", return_value="test-model")
@pytest.mark.anyio
async def test_chat_streaming(_mock_default, _mock_ensure, _mock_history, _mock_save, mock_builder):
    from web.routers.chat import chat

    mock_builder.return_value = lambda: iter([
        '{"t":"reasoning","d":"Thinking..."}\n',
        '{"t":"content","d":"Hello from mocked LLM"}\n',
    ])

    response = await chat("test-session-abc", BackgroundTasks(), message="hello", model="test-model")
    assert isinstance(response, StreamingResponse)
    assert response.media_type == "application/x-ndjson"


@patch("web.routers.sessions.rename_session")
@pytest.mark.anyio
async def test_rename_session(_mock_rename):
    from web.routers.sessions import rename
    await ensure_session("test-session-abc")

    response = await rename("test-session-abc", name="New Chat Name")
    assert isinstance(response, JSONResponse)
    assert b"ok" in response.body


@patch("web.routers.sessions.delete_session")
@pytest.mark.anyio
async def test_delete_session(_mock_delete):
    from web.routers.sessions import delete
    await ensure_session("test-session-abc")

    response = await delete("test-session-abc")
    assert isinstance(response, JSONResponse)
    assert b"ok" in response.body


@patch("web.routers.debug.get_debug_info", return_value={})
@pytest.mark.anyio
async def test_debug_info_empty(_mock_debug):
    from web.routers.debug import debug_info
    await ensure_session("test-session-abc")

    response = await debug_info("test-session-abc")
    assert isinstance(response, JSONResponse)
    assert response.body == b"{}"
