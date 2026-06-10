from unittest.mock import patch, MagicMock

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

from web.routers.pages import router, get_available_model_ids


def test_router_exists():
    assert isinstance(router, APIRouter)


def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/" in paths
    assert "/sessions/{session_id}" in paths
    assert "/sidebar" in paths
    assert "/sessions/{session_id}/messages" in paths
    assert "/favicon.ico" in paths


@patch("src.api.PRIORITY", ["model-a", "model-b"])
@patch("src.api.get_verified_models", return_value=["model-c", "model-a"])
def test_get_available_model_ids_includes_all(mock_verified):
    """Returns priority models first, then any additional verified models not in priority."""
    result = get_available_model_ids()
    # order: PRIORITY order first, then extras
    assert result == ["model-a", "model-b", "model-c"]


@patch("src.api.PRIORITY", ["model-a"])
@patch("src.api.get_verified_models", return_value=["model-a", "model-b"])
def test_get_available_model_ids_no_duplicates(mock_verified):
    """Duplicate model IDs should not appear twice."""
    result = get_available_model_ids()
    assert result == ["model-a", "model-b"]


@patch("src.api.PRIORITY", ["model-a"])
@patch("src.api.get_verified_models", side_effect=Exception("API fail"))
def test_get_available_model_ids_fallback_on_error(mock_verified):
    """If get_verified_models raises, fallback list is used."""
    result = get_available_model_ids()
    assert result == ["model-a", "deepseek-v4-flash-free"]


class TestPageEndpoints:
    """Verify page endpoint functions return correct response types."""

    @patch("web.routers.pages.get_default_model", return_value="m1")
    @patch("web.routers.pages.get_available_model_ids", return_value=["m1", "m2"])
    @patch("web.routers.pages.templates.TemplateResponse")
    def test_home_returns_html(self, mock_tpl, mock_models, mock_default):
        request = MagicMock()
        mock_tpl.return_value = HTMLResponse("<html></html>")
        from web.routers.pages import home
        resp = home(request)
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.get_default_model", return_value="m1")
    @patch("web.routers.pages.get_available_model_ids", return_value=["m1"])
    @patch("web.routers.pages.templates.TemplateResponse")
    def test_session_page_returns_html(self, mock_tpl, mock_models, mock_default):
        request = MagicMock()
        mock_tpl.return_value = HTMLResponse("<html></html>")
        from web.routers.pages import session_page
        resp = session_page(request, "sid-1")
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.get_sessions", return_value=[])
    @patch("web.routers.pages.templates.TemplateResponse")
    def test_sidebar_returns_html(self, mock_tpl, mock_sessions):
        request = MagicMock()
        request.query_params.get.return_value = ""
        mock_tpl.return_value = HTMLResponse("<div></div>")
        from web.routers.pages import sidebar
        resp = sidebar(request)
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.render_session_messages", return_value="<div>msg</div>")
    def test_session_messages_returns_html(self, mock_render):
        from web.routers.pages import session_messages
        resp = session_messages("sid-1")
        assert isinstance(resp, HTMLResponse)
        assert b"<div>msg</div>" in resp.body

    def test_favicon_returns_file(self):
        from web.routers.pages import favicon
        resp = favicon()
        assert isinstance(resp, FileResponse)
