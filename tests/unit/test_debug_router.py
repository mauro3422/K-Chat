import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from web.routers.debug import router, _local_only, debug_info, backend_logs


@pytest.mark.anyio
async def test_router_exists():
    assert isinstance(router, APIRouter)


@pytest.mark.anyio
async def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/sessions/{session_id}/debug" in paths
    assert "/debug/backend-logs" in paths


class TestLocalOnly:
    @pytest.mark.anyio
    async def test_localhost_ipv4_passes(self):
        request = MagicMock()
        request.client.host = "127.0.0.1"
        _local_only(request)  # should not raise

    @pytest.mark.anyio
    async def test_localhost_ipv6_passes(self):
        request = MagicMock()
        request.client.host = "::1"
        _local_only(request)  # should not raise

    @pytest.mark.anyio
    async def test_localhost_name_passes(self):
        request = MagicMock()
        request.client.host = "localhost"
        _local_only(request)  # should not raise

    @pytest.mark.anyio
    async def test_non_local_ip_raises_403(self, monkeypatch):
        monkeypatch.delenv("TESTING", raising=False)
        request = MagicMock()
        request.client.host = "192.168.1.1"
        with pytest.raises(HTTPException) as exc:
            _local_only(request)
        assert exc.value.status_code == 403

    @pytest.mark.anyio
    async def test_testing_env_skips_check(self, monkeypatch):
        monkeypatch.setenv("TESTING", "true")
        request = MagicMock()
        request.client.host = "evil.com"
        _local_only(request)  # should not raise because TESTING=true

    @pytest.mark.anyio
    async def test_no_client_uses_unknown_fallback(self, monkeypatch):
        """When request.client is None, host becomes 'unknown' which is non-local."""
        monkeypatch.delenv("TESTING", raising=False)
        request = MagicMock()
        request.client = None
        with pytest.raises(HTTPException) as exc:
            _local_only(request)
        assert exc.value.status_code == 403


@pytest.mark.anyio
@patch("web.routers.debug.get_repos")
async def test_debug_info_missing_session_returns_404(mock_get_repos):
    mock_repos = MagicMock()
    mock_repos.sessions = AsyncMock()
    mock_repos.sessions.require_session = AsyncMock(side_effect=ValueError("Session not found"))
    mock_get_repos.return_value = mock_repos
    with pytest.raises(HTTPException) as exc:
        await debug_info("nonexistent")
    assert exc.value.status_code == 404


@pytest.mark.anyio
@patch("web.routers.debug.get_repos")
async def test_debug_info_returns_json(mock_get_repos):
    mock_repos = MagicMock()
    mock_repos.sessions = AsyncMock()
    mock_repos.debug = MagicMock()
    mock_repos.debug.get_info = AsyncMock()
    mock_repos.debug.get_info.return_value = {"key": "val"}
    mock_get_repos.return_value = mock_repos
    result = await debug_info("sid-1")
    assert isinstance(result, JSONResponse)
    import json
    body = json.loads(result.body.decode())
    assert body == {"key": "val"}
    mock_repos.debug.get_info.assert_called_once_with("sid-1")


@pytest.mark.anyio
@patch("web.routers.debug.get_backend_logs", return_value=[{"message": "log1"}, {"message": "log2"}])
async def test_backend_logs_returns_json(mock_logs):
    result = backend_logs()
    assert isinstance(result, JSONResponse)
    import json
    body = json.loads(result.body.decode())
    assert body == {"logs": [{"message": "log1"}, {"message": "log2"}]}
