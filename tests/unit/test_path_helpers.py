import pytest
from unittest.mock import AsyncMock
from unittest.mock import patch

from src.tools._path_helpers import validate_path


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_within_context_dir(mock_realpath, mock_expanduser):
    result = validate_path("src/file.py", "/home/user/project/src/file.py")
    assert result is None


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_within_home(mock_realpath, mock_expanduser):
    result = validate_path("~/docs/note.txt", "/home/user/docs/note.txt")
    assert result is None


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_within_tmp(mock_realpath, mock_expanduser):
    result = validate_path("/tmp/foo/bar", "/tmp/foo/bar")
    assert result is None


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_outside_all_dirs(mock_realpath, mock_expanduser):
    result = validate_path("/etc/passwd", "/etc/passwd")
    assert result is not None
    assert "Access denied" in result


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_traversal_escapes_project(mock_realpath, mock_expanduser):
    result = validate_path("../file.txt", "/home/user/file.txt")
    assert result is None  # allowed — still within $HOME


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@pytest.mark.anyio
async def test_validate_symlink_resolves_to_allowed(mock_expanduser):
    def _realpath(p):
        link_map = {
            "/tmp/link/target.txt": "/home/user/project/actual/target.txt",
        }
        return link_map.get(p, p)

    with patch("src.tools._path_helpers.os.path.realpath", side_effect=_realpath):
        result = validate_path("/tmp/link/target.txt", "/tmp/link/target.txt")
    assert result is None


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@pytest.mark.anyio
async def test_validate_symlink_resolves_outside(mock_expanduser):
    def _realpath(p):
        link_map = {
            "/home/user/project/link": "/etc/outside",
        }
        return link_map.get(p, p)

    with patch("src.tools._path_helpers.os.path.realpath", side_effect=_realpath):
        result = validate_path("link", "/home/user/project/link")
    assert result is not None
    assert "Access denied" in result


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_deeply_nested(mock_realpath, mock_expanduser):
    result = validate_path(
        "sub/deep/nested/file.txt",
        "/home/user/project/sub/deep/nested/file.txt",
    )
    assert result is None


@patch("src.tools._path_helpers.CONTEXT_DIR", "/home/user/project")
@patch("src.tools._path_helpers.os.path.expanduser", return_value="/home/user")
@patch("src.tools._path_helpers.os.path.realpath", side_effect=lambda p: p)
@pytest.mark.anyio
async def test_validate_root_is_denied(mock_realpath, mock_expanduser):
    result = validate_path("/", "/")
    assert result is not None
