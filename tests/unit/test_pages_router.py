import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

from web.routers.pages import router, get_available_model_ids


@pytest.mark.anyio
async def test_router_exists():
    assert isinstance(router, APIRouter)


@pytest.mark.anyio
async def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/" in paths
    assert "/sessions/{session_id}" in paths
    assert "/sidebar" in paths
    assert "/sessions/{session_id}/messages" in paths
    assert "/favicon.ico" in paths


@patch("web.routers.pages.PRIORITY", ["model-a", "model-b"])
@patch("web.routers.pages.get_verified_models_safe", return_value=["model-c", "model-a"])
@pytest.mark.anyio
async def test_get_available_model_ids_includes_all(mock_verified):
    """Returns priority models first, then any additional verified models not in priority."""
    result = get_available_model_ids()
    # order: PRIORITY order first, then extras
    assert result == ["model-a", "model-b", "model-c"]


@patch("web.routers.pages.PRIORITY", ["model-a"])
@patch("web.routers.pages.get_verified_models_safe", return_value=["model-a", "model-b"])
@pytest.mark.anyio
async def test_get_available_model_ids_no_duplicates(mock_verified):
    """Duplicate model IDs should not appear twice."""
    result = get_available_model_ids()
    assert result == ["model-a", "model-b"]


@patch("web.routers.pages.PRIORITY", ["model-a"])
@patch("web.routers.pages.get_verified_models_safe", return_value=None)
@pytest.mark.anyio
async def test_get_available_model_ids_fallback_on_error(mock_verified):
    """If get_verified_models raises, fallback list is used."""
    result = get_available_model_ids()
    assert result == ["model-a", "deepseek-v4-flash-free"]


class TestPageEndpoints:
    """Verify page endpoint functions return correct response types."""

    @patch("web.routers.pages.get_available_model_ids", return_value=["m1", "m2"])
    @patch("web.routers.pages.templates.TemplateResponse")
    @pytest.mark.anyio
    async def test_home_returns_html(self, mock_tpl, mock_models):
        request = MagicMock()
        mock_tpl.return_value = HTMLResponse("<html></html>")
        from web.routers.pages import home
        resp = home(request)
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.get_available_model_ids", return_value=["m1"])
    @patch("web.routers.pages.templates.TemplateResponse")
    @pytest.mark.anyio
    async def test_session_page_returns_html(self, mock_tpl, mock_models):
        request = MagicMock()
        mock_tpl.return_value = HTMLResponse("<html></html>")
        from web.routers.pages import session_page
        resp = session_page(request, "sid-1")
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.get_sessions", new_callable=AsyncMock)
    @patch("web.routers.pages.templates.TemplateResponse")
    @pytest.mark.anyio
    async def test_sidebar_returns_html(self, mock_tpl, mock_sessions):
        request = MagicMock()
        request.query_params.get.return_value = ""
        mock_tpl.return_value = HTMLResponse("<div></div>")
        from web.routers.pages import sidebar
        resp = await sidebar(request)
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.render_session_messages", new_callable=AsyncMock)
    @pytest.mark.anyio
    async def test_session_messages_returns_dict(self, mock_render):
        from web.routers.pages import session_messages
        mock_render.return_value = {"messages": [], "widget_states": {}}
        resp = await session_messages("sid-1")
        assert isinstance(resp, dict)
        assert "messages" in resp


    @pytest.mark.anyio
    async def test_favicon_returns_file(self):
        from web.routers.pages import favicon
        resp = favicon()
        assert isinstance(resp, FileResponse)
