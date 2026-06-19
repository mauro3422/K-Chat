import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch, MagicMock

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, FileResponse

from web.routers.pages import router, get_available_model_ids
from web.routers.pages import get_available_models


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
@patch("web.routers.pages.get_model_registry")
@pytest.mark.anyio
async def test_get_available_model_ids_includes_all(mock_registry, mock_verified):
    """Returns priority models first, then any additional verified models not in priority."""
    mock_registry.return_value.get_all_models.return_value = ["model-a", "model-b", "model-c"]
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
@patch("web.routers.pages.get_model_registry")
@pytest.mark.anyio
async def test_get_available_model_ids_fallback_on_error(mock_registry, mock_verified):
    """If get_verified_models raises, fallback list is used."""
    mock_registry.return_value.get_all_models.return_value = ["model-a"]
    result = get_available_model_ids()
    assert result == ["model-a", "deepseek-v4-flash"]


class TestPageEndpoints:
    """Verify page endpoint functions return correct response types."""

    @patch("web.routers.pages.get_available_model_ids", return_value=["m1", "m2"])
    @patch("web.routers.pages.templates.TemplateResponse")
    @patch("web.routers.pages.get_available_models", return_value={"go_standard": [{"id": "m1", "label": "m1", "tier": "go_standard"}]})
    @pytest.mark.anyio
    async def test_home_returns_html(self, mock_models_full, mock_tpl, mock_models):
        request = MagicMock()
        mock_tpl.return_value = HTMLResponse("<html></html>")
        from web.routers.pages import home
        resp = home(request)
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.get_available_model_ids", return_value=["m1"])
    @patch("web.routers.pages.templates.TemplateResponse")
    @patch("web.routers.pages.get_available_models", return_value={"go_standard": [{"id": "m1", "label": "m1", "tier": "go_standard"}]})
    @pytest.mark.anyio
    async def test_session_page_returns_html(self, mock_models_full, mock_tpl, mock_models):
        request = MagicMock()
        mock_tpl.return_value = HTMLResponse("<html></html>")
        from web.routers.pages import session_page
        resp = session_page(request, "sid-1")
        assert isinstance(resp, HTMLResponse)

    @patch("web.routers.pages.get_repos")
    @patch("web.routers.pages.templates.TemplateResponse")
    @pytest.mark.anyio
    async def test_sidebar_returns_html(self, mock_tpl, mock_get_repos):
        mock_repos = MagicMock()
        mock_repos.sessions = AsyncMock()
        mock_repos.sessions.get_all.return_value = []
        mock_get_repos.return_value = mock_repos
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
        resp = await session_messages(MagicMock(), "sid-1")
        assert isinstance(resp, dict)
        assert "messages" in resp

    @pytest.mark.anyio
    def test_get_available_models_uses_request_state(self):
        class FakeRegistry:
            def get_all_models(self):
                return ["alpha-free", "beta-go"]

            def get_tier(self, model_id):
                return "free_ratelimited" if model_id.endswith("-free") else "go_standard"

        class FakeRateStore:
            def get_cooldown_remaining(self, model_id):
                return 12 if model_id == "alpha-free" else None

        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            model_registry=FakeRegistry(),
            rate_limit_store=FakeRateStore(),
        )))
        with patch("web.routers.pages.PRIORITY", []), patch("web.routers.pages.get_verified_models_safe", return_value=["alpha-free", "beta-go"]):
            models = get_available_models(request=request)
        assert models["free_ratelimited"][0]["id"] == "alpha-free"
        assert "12s" in models["free_ratelimited"][0]["label"]
        assert models["go_standard"][0]["id"] == "beta-go"


    @pytest.mark.anyio
    async def test_favicon_returns_file(self):
        from web.routers.pages import favicon
        resp = favicon()
        assert isinstance(resp, FileResponse)
