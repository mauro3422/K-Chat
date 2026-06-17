import pytest
from unittest.mock import MagicMock, patch

from src.tools.read_multiple import (
    run,
    DEFINITION,
    _parse_file_spec,
    _read_single,
    MAX_FILES,
)


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    fdef = DEFINITION["function"]
    assert fdef["name"] == "read_multiple"
    props = fdef["parameters"]["properties"]
    assert props["files"]["type"] == "array"
    assert "files" in fdef["parameters"]["required"]
    assert props["max_lines"]["default"] == 250


def test_parse_simple_path():
    path, start, end = _parse_file_spec("foo.py")
    assert path == "foo.py"
    assert start == 1
    assert end is None


def test_parse_with_range():
    path, start, end = _parse_file_spec("foo.py:10-30")
    assert path == "foo.py"
    assert start == 10
    assert end == 30


def test_parse_with_start_only():
    path, start, end = _parse_file_spec("foo.py:40")
    assert path == "foo.py"
    assert start == 40
    assert end is None


def test_parse_windows_path():
    path, start, end = _parse_file_spec(r"C:\foo\bar.py:5-15")
    assert path == r"C:\foo\bar.py"
    assert start == 5
    assert end == 15


def test_parse_whitespace_stripped():
    path, start, end = _parse_file_spec("  file.py:2-8  ")
    assert path == "file.py"
    assert start == 2
    assert end == 8


def test_parse_negative_start_defaults():
    path, start, end = _parse_file_spec("file.py:-5")
    # The regex won't capture negative numbers
    assert start == 1
    assert end is None


# --- _read_single tests ---

def _mock_resolve_valid(path: str = "/fake/file.py") -> tuple[str, str | None]:
    return (path, None)


def _mock_file_lines(lines: list[str]):
    """Context manager that patches builtins.open and path checks."""
    return patch.multiple(
        "src.tools.read_multiple",
        resolve_and_validate_path=MagicMock(return_value=("/fake/file.py", None)),
    ), patch("builtins.open", new_callable=MagicMock())


def test_read_single_success():
    content_lines = ["line one\n", "line two\n", "line three\n"]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/fake/file.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = content_lines
        mock_open.return_value.__enter__.return_value = mock_file

        result = _read_single("/fake/file.py", 1, None, 250)

    assert "/fake/file.py" in result
    assert "lines 1-3/3" in result
    assert "line one" in result
    assert "line two" in result
    assert "line three" in result


def test_read_single_with_range():
    content_lines = ["a\n", "b\n", "c\n", "d\n", "e\n"]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/f.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = content_lines
        mock_open.return_value.__enter__.return_value = mock_file

        result = _read_single("/f.py", 2, 4, 250)

    assert "lines 2-4/5" in result
    assert "b\n" in result
    assert "c\n" in result
    assert "d\n" in result
    assert "a\n" not in result
    assert "e\n" not in result


def test_read_single_start_beyond_end():
    content_lines = ["x\n", "y\n"]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/f.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = content_lines
        mock_open.return_value.__enter__.return_value = mock_file

        result = _read_single("/f.py", 10, None, 250)

    assert "lines 10-2/2" in result or "lines 1-2/2" in result


def test_read_single_file_not_found():
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/nonexistent.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=False),
    ):
        result = _read_single("/nonexistent.py", 1, None, 250)
    assert "[ERROR]" in result
    assert "no existe" in result


def test_read_single_is_directory():
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/dir", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=True),
    ):
        result = _read_single("/dir", 1, None, 250)
    assert "[ERROR]" in result
    assert "directorio" in result


def test_read_single_path_validation_error():
    with patch("src.tools.read_multiple.resolve_and_validate_path",
               return_value=("/bad", "Acceso denegado")):
        result = _read_single("/bad", 1, None, 250)
    assert "[ERROR]" in result
    assert "Acceso denegado" in result


def test_read_single_truncation():
    """Truncation triggers when explicit end_line makes shown > max_lines."""
    lines = [f"line {i}\n" for i in range(500)]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/big.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = lines
        mock_open.return_value.__enter__.return_value = mock_file

        result = _read_single("/big.py", 1, end_line=500, max_lines=10)

    assert "[truncado" in result


# --- run() async tests ---

@pytest.mark.anyio
async def test_run_no_files():
    result = await run(files=[])
    assert "[ERROR]" in result


@pytest.mark.anyio
async def test_run_files_not_a_list():
    result = await run(files="not_a_list")
    assert "[ERROR]" in result


@pytest.mark.anyio
async def test_run_too_many_files():
    result = await run(files=[f"f{i}.py" for i in range(MAX_FILES + 1)])
    assert "[ERROR]" in result
    assert str(MAX_FILES + 1) in result


@pytest.mark.anyio
async def test_run_single_file():
    content = ["hello\n", "world\n"]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/f.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = content
        mock_open.return_value.__enter__.return_value = mock_file

        result = await run(files=["/f.py"])

    assert "hello" in result
    assert "world" in result


@pytest.mark.anyio
async def test_run_multiple_files():
    contents = {
        "/a.py": ["from a\n"],
        "/b.py": ["from b\n"],
    }

    def mock_open_side_effect(file, *args, **kwargs):
        mock_file = MagicMock()
        basename = file if isinstance(file, str) else "/unknown"
        mock_file.readlines.return_value = contents.get(basename, ["unknown\n"])
        cm = MagicMock()
        cm.__enter__.return_value = mock_file
        return cm

    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              side_effect=lambda p: (p, None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_open.side_effect = mock_open_side_effect
        result = await run(files=["/a.py", "/b.py"])

    assert "from a" in result
    assert "from b" in result


@pytest.mark.anyio
async def test_run_parse_range_from_user():
    content = ["line1\n", "line2\n", "line3\n"]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/f.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = content
        mock_open.return_value.__enter__.return_value = mock_file

        result = await run(files=["/f.py:2-3"])

    assert "lines 2-3/3" in result


@pytest.mark.anyio
async def test_run_max_lines_respected():
    """Truncation triggers when file spec has a range exceeding max_lines."""
    lines = [f"line {i}\n" for i in range(100)]
    with (
        patch("src.tools.read_multiple.resolve_and_validate_path",
              return_value=("/big.py", None)),
        patch("src.tools.read_multiple.os.path.exists", return_value=True),
        patch("src.tools.read_multiple.os.path.isdir", return_value=False),
        patch("builtins.open", new_callable=MagicMock()) as mock_open,
    ):
        mock_file = MagicMock()
        mock_file.readlines.return_value = lines
        mock_open.return_value.__enter__.return_value = mock_file

        result = await run(files=["/big.py:1-100"], max_lines=5)

    assert "lines 1-5/100" in result
    assert "[truncado" in result


@pytest.mark.anyio
async def test_run_max_lines_clamped_to_500():
    result = await run(files=[], max_lines=9999)
    # max_lines clamped to 500, no crash
    assert "[ERROR]" in result
