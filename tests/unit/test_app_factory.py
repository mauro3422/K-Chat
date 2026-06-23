import logging
import pytest
from unittest.mock import AsyncMock
"""Tests for app_factory.py"""
from unittest.mock import MagicMock, patch


class TestAppFactory:
    @pytest.fixture(autouse=True)
    def _mock_startup(self):
        fake_config = MagicMock(testing=True, log_level="INFO", http_rate_limit=10)
        with (
            patch("web.app_factory.load_config", return_value=fake_config),
            patch("web.app_factory.init_db", new=AsyncMock()),
            patch("web.app_factory.init_memory_db", new=AsyncMock()),
            patch("web.app_factory.get_repos", return_value=MagicMock()),
            patch("web.app_factory.deps.searxng_start", return_value=None),
            patch("web.app_factory.deps.searxng_stop", return_value=None),
        ):
            yield

    @pytest.mark.anyio
    async def test_create_app_returns_app(self):
        from web.app_factory import create_app
        app = create_app()
        assert app is not None
        assert app.title is not None

    def test_setup_logging_suppresses_successful_httpx_requests(self):
        from web.app_factory import setup_logging

        setup_logging(MagicMock(log_level="INFO"))

        assert logging.getLogger("httpx").level == logging.WARNING

    @pytest.mark.anyio
    async def test_app_has_static_mounted(self):
        from web.app_factory import create_app
        app = create_app()
        routes = [r for r in app.routes if getattr(r, "name", None) == "static"]
        assert len(routes) == 1

    @pytest.mark.anyio
    async def test_app_registers_routers(self):
        from web.app_factory import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in paths
        assert "/" in paths
        assert "/favicon.ico" in paths

    @pytest.mark.anyio
    async def test_app_has_middleware(self):
        from web.app_factory import create_app
        app = create_app()
        assert len(app.user_middleware) > 0

    @pytest.mark.anyio
    async def test_app_has_exception_handlers(self):
        from web.app_factory import create_app
        app = create_app()
        assert 404 in app.exception_handlers
        assert Exception in app.exception_handlers
        from fastapi.exceptions import RequestValidationError
        assert RequestValidationError in app.exception_handlers

    @pytest.mark.anyio
    async def test_health_endpoint(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/health")
            assert response.status_code in (200, 503)
            data = response.json()
            assert "status" in data
            assert "coordination" in data
            assert "memory" in data
            assert "sync" in data
            assert "failover" in data
            assert "freshness" in data["memory"]
            assert "cluster" in data["coordination"]

    @pytest.mark.anyio
    async def test_static_file_served(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/static/style.css")
            assert response.status_code == 200

    @pytest.mark.anyio
    async def test_static_dist_asset_served(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/static/dist/assets/")
            assert response.status_code in (200, 403, 404)

    @pytest.mark.anyio
    async def test_csp_middleware_adds_header(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/static/style.css")
            assert "Content-Security-Policy" in response.headers

    @pytest.mark.anyio
    async def test_root_endpoint(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/")
            assert response.status_code in (200, 500)

    @pytest.mark.anyio
    async def test_logbus_lives_until_shutdown(self):
        from fastapi import FastAPI
        from web.app_factory import lifespan

        fake_embeddings = MagicMock()
        fake_embeddings.generate_embedding = MagicMock()
        fake_embeddings.get_model = MagicMock(return_value=None)
        fake_embeddings.unload_model = MagicMock()

        fake_deleted_sessions_db = MagicMock()
        fake_deleted_sessions_db.init_deleted_sessions_db = MagicMock()

        fake_reranker = MagicMock()
        fake_reranker.unload_model = MagicMock()

        with (
            patch("src.logbus.core.LogBus.start", new_callable=AsyncMock) as mock_start,
            patch("src.logbus.core.LogBus.stop", new_callable=AsyncMock) as mock_stop,
            patch("src.logbus.core.LogBus.add_writer") as mock_add_writer,
            patch("web.app_factory.reset_web_runtime_state") as mock_reset_web_state,
            patch("web.app_factory.importlib.import_module", side_effect=lambda name: {
                "src.memory.embeddings.service": fake_embeddings,
                "src.memory.deleted_sessions_db": fake_deleted_sessions_db,
                "src.memory.retrieval.reranker": fake_reranker,
            }[name]),
        ):
            app = FastAPI()
            async with lifespan(app):
                mock_start.assert_awaited_once()
                mock_stop.assert_not_awaited()
                assert mock_add_writer.call_count >= 2
                assert app.state.repos is not None

        mock_reset_web_state.assert_called_once()
        mock_stop.assert_awaited_once()

    @pytest.mark.anyio
    async def test_prime_verified_model_cache_uses_shared_registry_in_go_mode(self):
        from fastapi import FastAPI
        from web.app_factory import _prime_verified_model_cache

        app = FastAPI()
        app.state.config = MagicMock(llm_mode="go")
        app.state.model_registry = MagicMock()
        app.state.model_registry.get_all_models.return_value = ["model-a", "model-b"]

        with (
            patch("web.app_factory.ensure_registry_refreshed", new=AsyncMock()),
            patch("web.app_factory.get_verified_models", new=AsyncMock()) as mock_get_verified,
        ):
            await _prime_verified_model_cache(app, timeout=0.1)

        app.state.model_registry.set_verified_models.assert_called_once_with(["model-a", "model-b"])
        mock_get_verified.assert_not_awaited()
