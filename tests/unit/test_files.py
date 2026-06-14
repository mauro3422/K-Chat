import pytest
from unittest.mock import AsyncMock
import os
from unittest.mock import patch, mock_open


@pytest.mark.anyio
async def test_ensure_file_creates():
    from src.context import _ensure_file

    with patch("os.path.exists", return_value=False):
        with patch("builtins.open", mock_open()) as m:
            _ensure_file("/tmp/test.md", "# content")
            m.assert_called_once_with("/tmp/test.md", "w", encoding="utf-8")
            m().write.assert_called_once_with("# content")


@pytest.mark.anyio
async def test_ensure_file_exists():
    from src.context import _ensure_file

    with patch("os.path.exists", return_value=True):
        with patch("builtins.open") as m:
            _ensure_file("/tmp/test.md", "# content")
            m.assert_not_called()


@pytest.mark.anyio
async def test_ensure_file_oserror():
    from src.context import _ensure_file

    with patch("os.path.exists", return_value=False):
        with patch("builtins.open", side_effect=OSError("permission denied")):
            _ensure_file("/tmp/test.md", "# content")


@pytest.mark.anyio
async def test_read_file_normal():
    from src.context import _read_file

    with patch("builtins.open", mock_open(read_data="  hello world  ")):
        result = _read_file("/tmp/test.md")
        assert result == "hello world"


@pytest.mark.anyio
async def test_read_file_missing():
    from src.context import _read_file

    with patch("builtins.open", side_effect=FileNotFoundError("no such file")):
        result = _read_file("/tmp/missing.md")
        assert result == ""


@pytest.mark.anyio
async def test_read_file_oserror():
    from src.context import _read_file

    with patch("builtins.open", side_effect=OSError("permission denied")):
        result = _read_file("/tmp/test.md")
        assert result == ""
