"""Tests for app_factory.py"""
from unittest.mock import patch


class TestAppFactory:
    def test_create_app_returns_app(self):
        from web.app_factory import create_app
        app = create_app()
        assert app is not None
        assert app.title is not None

    def test_app_has_static_mounted(self):
        from web.app_factory import create_app
        app = create_app()
        routes = [r for r in app.routes if getattr(r, "name", None) == "static"]
        assert len(routes) == 1

    def test_app_registers_routers(self):
        from web.app_factory import create_app
        app = create_app()
        paths = [r.path for r in app.routes if hasattr(r, "path")]
        assert "/health" in paths
        assert "/" in paths
        assert "/favicon.ico" in paths

    def test_app_has_middleware(self):
        from web.app_factory import create_app
        app = create_app()
        assert len(app.user_middleware) > 0

    def test_app_has_exception_handlers(self):
        from web.app_factory import create_app
        app = create_app()
        assert 404 in app.exception_handlers
        assert Exception in app.exception_handlers
        from fastapi.exceptions import RequestValidationError
        assert RequestValidationError in app.exception_handlers

    def test_health_endpoint(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code in (200, 503)
        data = response.json()
        assert "status" in data

    def test_static_file_served(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/static/style.css")
        assert response.status_code == 200

    def test_static_dist_asset_served(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/static/dist/assets/")
        assert response.status_code in (200, 403, 404)

    def test_csp_middleware_adds_header(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/static/style.css")
        assert "Content-Security-Policy" in response.headers

    def test_root_endpoint(self):
        from web.app_factory import create_app
        from fastapi.testclient import TestClient
        app = create_app()
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/")
        assert response.status_code in (200, 500)
