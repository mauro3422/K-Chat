import pytest
from unittest.mock import AsyncMock, patch

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from web.routers.sessions import router, rename, delete


@pytest.mark.anyio
async def test_router_exists():
    assert isinstance(router, APIRouter)


@pytest.mark.anyio
async def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/sessions/{session_id}/rename" in paths
    assert "/sessions/{session_id}/delete" in paths


@patch("web.routers.sessions.rename_session", new_callable=AsyncMock)
@patch("web.routers.sessions._require_session", new_callable=AsyncMock)
@pytest.mark.anyio
async def test_rename_success(mock_req, mock_rename):
    result = await rename("sid-1", name="New Name")
    assert isinstance(result, JSONResponse)
    mock_rename.assert_called_once_with("sid-1", "New Name")


@patch("web.routers.sessions.rename_session", new_callable=AsyncMock)
@patch("web.routers.sessions._require_session", new_callable=AsyncMock)
@pytest.mark.anyio
async def test_rename_strips_whitespace(mock_req, mock_rename):
    await rename("sid-1", name="   Trimmed   ")
    mock_rename.assert_called_once_with("sid-1", "Trimmed")


@patch("web.routers.sessions.rename_session", new_callable=AsyncMock)
@patch("web.routers.sessions._require_session", new_callable=AsyncMock)
@pytest.mark.anyio
async def test_rename_empty_name_fallback(mock_req, mock_rename):
    await rename("long-session-id", name="   ")
    mock_rename.assert_called_once_with("long-session-id", "long-ses")


@patch("web.routers.sessions.delete_session", new_callable=AsyncMock)
@patch("web.routers.sessions.get_repos")
@patch("web.routers.sessions._require_session", new_callable=AsyncMock)
@pytest.mark.anyio
async def test_delete_success(mock_req, mock_get_repos, mock_delete):
    result = await delete("sid-1")
    assert isinstance(result, JSONResponse)
    mock_delete.assert_called_once_with("sid-1", repos=mock_get_repos.return_value)
