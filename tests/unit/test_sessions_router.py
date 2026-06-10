from unittest.mock import patch

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from web.routers.sessions import router, rename, delete


def test_router_exists():
    assert isinstance(router, APIRouter)


def test_router_has_routes():
    assert len(router.routes) >= 1
    paths = [r.path for r in router.routes]
    assert "/sessions/{session_id}/rename" in paths
    assert "/sessions/{session_id}/delete" in paths


@patch("web.routers.sessions.rename_session")
def test_rename_success(mock_rename):
    """Rename with a valid name calls rename_session and returns OK."""
    result = rename("sid-1", name="New Name")
    assert isinstance(result, HTMLResponse)
    assert result.body == b"OK"
    mock_rename.assert_called_once_with("sid-1", "New Name")


@patch("web.routers.sessions.rename_session")
def test_rename_strips_whitespace(mock_rename):
    """Rename strips whitespace from name before passing to rename_session."""
    rename("sid-1", name="   Trimmed   ")
    mock_rename.assert_called_once_with("sid-1", "Trimmed")


@patch("web.routers.sessions.rename_session")
def test_rename_empty_name_fallback(mock_rename):
    """Empty name after strip falls back to session_id[:8]."""
    rename("long-session-id", name="   ")
    mock_rename.assert_called_once_with("long-session-id", "long-ses")


@patch("web.routers.sessions.delete_session")
def test_delete_success(mock_delete):
    """Delete calls delete_session and returns OK."""
    result = delete("sid-1")
    assert isinstance(result, HTMLResponse)
    assert result.body == b"OK"
    mock_delete.assert_called_once_with("sid-1")
