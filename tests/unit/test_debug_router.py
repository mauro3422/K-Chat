import pytest
from unittest.mock import MagicMock, patch

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from web.routers.debug import router, _local_only, debug_info, backend_logs


def test_router_exists():
    assert isinstance(router, APIRouter)


def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/sessions/{session_id}/debug" in paths
    assert "/debug/backend-logs" in paths


class TestLocalOnly:
    def test_localhost_ipv4_passes(self):
        request = MagicMock()
        request.client.host = "127.0.0.1"
        _local_only(request)  # should not raise

    def test_localhost_ipv6_passes(self):
        request = MagicMock()
        request.client.host = "::1"
        _local_only(request)  # should not raise

    def test_localhost_name_passes(self):
        request = MagicMock()
        request.client.host = "localhost"
        _local_only(request)  # should not raise

    def test_non_local_ip_raises_403(self, monkeypatch):
        monkeypatch.delenv("TESTING", raising=False)
        request = MagicMock()
        request.client.host = "192.168.1.1"
        with pytest.raises(HTTPException) as exc:
            _local_only(request)
        assert exc.value.status_code == 403

    def test_testing_env_skips_check(self, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        request = MagicMock()
        request.client.host = "evil.com"
        _local_only(request)  # should not raise because TESTING=true

    def test_no_client_uses_unknown_fallback(self, monkeypatch):
        """When request.client is None, host becomes 'unknown' which is non-local."""
        monkeypatch.delenv("TESTING", raising=False)
        request = MagicMock()
        request.client = None
        with pytest.raises(HTTPException) as exc:
            _local_only(request)
        assert exc.value.status_code == 403


@patch("web.routers.debug.get_debug_info", return_value={"key": "val"})
def test_debug_info_returns_json(mock_debug):
    result = debug_info("sid-1")
    assert isinstance(result, JSONResponse)
    import json
    body = json.loads(result.body.decode())
    assert body == {"key": "val"}
    mock_debug.assert_called_once_with("sid-1")


@patch("web.routers.debug.get_backend_logs", return_value=[{"message": "log1"}, {"message": "log2"}])
def test_backend_logs_returns_json(mock_logs):
    result = backend_logs()
    assert isinstance(result, JSONResponse)
    import json
    body = json.loads(result.body.decode())
    assert body == {"logs": [{"message": "log1"}, {"message": "log2"}]}
