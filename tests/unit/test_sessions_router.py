import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from web.routers.sessions import router, rename, delete


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


@patch("web.routers.sessions.get_repos")
@pytest.mark.anyio
async def test_rename_success(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    result = await rename("sid-1", name="New Name")
    assert isinstance(result, JSONResponse)
    repos.sessions.rename.assert_called_once_with("sid-1", "New Name")


@patch("web.routers.sessions.get_repos")
@pytest.mark.anyio
async def test_rename_strips_whitespace(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    await rename("sid-1", name="   Trimmed   ")
    repos.sessions.rename.assert_called_once_with("sid-1", "Trimmed")


@patch("web.routers.sessions.get_repos")
@pytest.mark.anyio
async def test_rename_empty_name_fallback(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    await rename("long-session-id", name="   ")
    repos.sessions.rename.assert_called_once_with("long-session-id", "long-ses")


@patch("web.routers.sessions.get_repos")
@pytest.mark.anyio
async def test_delete_success(mock_get_repos):
    repos = MagicMock()
    repos.sessions = AsyncMock()
    mock_get_repos.return_value = repos
    result = await delete("sid-1")
    assert isinstance(result, JSONResponse)
    repos.sessions.delete_cascade.assert_called_once_with("sid-1", repos=repos)
