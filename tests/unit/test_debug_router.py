import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from web.routers.debug import router, _local_only, debug_info, backend_logs
from web.routers.debug import model_availability


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
    mock_repos = SimpleNamespace(sessions=SimpleNamespace(require_session=AsyncMock(side_effect=ValueError("Session not found"))))
    mock_get_repos.return_value = mock_repos
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    with pytest.raises(HTTPException) as exc:
        await debug_info("nonexistent", request)
    assert exc.value.status_code == 404


@pytest.mark.anyio
@patch("web.routers.debug.get_repos")
async def test_debug_info_returns_json(mock_get_repos):
    mock_repos = SimpleNamespace(
        sessions=SimpleNamespace(require_session=AsyncMock(return_value=None)),
        debug=SimpleNamespace(get_info=AsyncMock(return_value={"key": "val"})),
    )
    mock_get_repos.return_value = mock_repos
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()))
    result = await debug_info("sid-1", request)
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


@pytest.mark.anyio
async def test_model_availability_uses_request_state(monkeypatch):
    monkeypatch.setenv("TESTING", "true")

    class FakeRateStore:
        def get_cooldown_remaining(self, model_id):
            return 5 if model_id == "alpha-free" else None

        def is_available(self, model_id):
            return model_id == "beta-go"

        def is_unavailable(self, model_id):
            return False

        def summary(self):
            return {"limited_count": 1}

    class FakeRegistry:
        def summary(self):
            return {"total_models": 2, "tier_counts": {"free_ratelimited": 1, "go_standard": 1}}

        def is_quota_exhausted(self):
            return False

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(
            rate_limit_store=FakeRateStore(),
            model_registry=FakeRegistry(),
        )),
        client=SimpleNamespace(host="127.0.0.1"),
    )

    with patch("web.routers.pages.get_available_model_ids", return_value=["alpha-free", "beta-go"]), \
         patch("web.routers.pages._get_model_tier", side_effect=["free_ratelimited", "go_standard"]):
        result = await model_availability(request)

    assert result["models"]["alpha-free"]["tier"] == "free_ratelimited"
    assert result["models"]["alpha-free"]["status"] == "rate_limited"
    assert result["models"]["beta-go"]["status"] == "available"
