import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from web.routers.sessions import router, rename, delete, list_sessions
from web.services.session_artifact_coordinator import SessionArtifactCoordinator


@pytest.fixture
def mock_repos():
    repos = MagicMock()
    repos.sessions = AsyncMock()
    return repos


@pytest.mark.anyio
async def test_router_exists():
    assert isinstance(router, APIRouter)


@pytest.mark.anyio
async def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/sessions/{session_id}/rename" in paths
    assert "/sessions/{session_id}/delete" in paths
    assert "/sessions" in paths


@patch("web.routers._node_helpers.get_repos")
@pytest.mark.anyio
async def test_rename_success(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    result = await rename("sid-1", name="New Name")
    assert isinstance(result, JSONResponse)
    repos.sessions.rename.assert_called_once_with("sid-1", "New Name")


@patch("web.routers._node_helpers.get_repos")
@pytest.mark.anyio
async def test_rename_strips_whitespace(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    await rename("sid-1", name="   Trimmed   ")
    repos.sessions.rename.assert_called_once_with("sid-1", "Trimmed")


@patch("web.routers._node_helpers.get_repos")
@pytest.mark.anyio
async def test_rename_empty_name_fallback(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    await rename("long-session-id", name="   ")
    repos.sessions.rename.assert_called_once_with("long-session-id", "long-ses")


@patch("web.routers._node_helpers.get_repos")
@pytest.mark.anyio
async def test_delete_success(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    event_bus = MagicMock()
    event_bus.publish = AsyncMock()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                repos=None,
                event_bus=event_bus,
                session_artifact_coordinator=SessionArtifactCoordinator(),
            )
        )
    )
    result = await delete("sid-1", request)
    assert isinstance(result, JSONResponse)
    repos.sessions.delete_cascade.assert_called_once_with("sid-1", repos=repos)


@patch("web.routers.sessions._request_bridge")
@patch("web.routers._node_helpers.get_repos")
@pytest.mark.anyio
async def test_list_sessions_federates_peer_directory(mock_get_repos, mock_request_bridge):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    repos.sessions.get_all.return_value = [
        ("local-1", "2026-06-19T10:00:00", "2026-06-19T11:00:00", 3, "Local Chat", None, 1),
    ]
    mock_get_repos.return_value = repos

    bridge = MagicMock()
    bridge.peer_urls = ["http://peer-a:8000"]
    bridge.request_session_directory = AsyncMock(return_value={
        "ok": True,
        "sessions": [
            {
                "id": "remote-1",
                "name": "Remote Chat",
                "count": 7,
                "last_str": "2026-06-19T12:00:00",
                "is_favorite": False,
                "node_id": "peer-a",
                "node_role": "secondary",
                "cluster_name": "kairos",
                "source_mode": "peer",
                "source_url": "http://peer-a:8000",
            }
        ],
    })
    mock_request_bridge.return_value = bridge

    result = await list_sessions()
    assert isinstance(result, JSONResponse)
    data = result.body.decode("utf-8")
    assert "local-1" in data
    assert "remote-1" in data
    assert "peer-a" in data
