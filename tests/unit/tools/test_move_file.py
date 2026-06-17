import os
import pytest

from src.tools.move_file import DEFINITION, run


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    func = DEFINITION["function"]
    assert func["name"] == "move_file"
    assert "source" in func["parameters"]["properties"]
    assert "dest" in func["parameters"]["properties"]
    assert func["parameters"]["required"] == ["source", "dest"]


@pytest.mark.anyio
async def test_move_file(tmp_path):
    src = tmp_path / "source.txt"
    dst = tmp_path / "moved.txt"
    src.write_text("hello")

    result = await run(source=str(src), dest=str(dst))

    assert result.startswith("[OK]")
    assert not src.exists()
    assert dst.read_text() == "hello"


@pytest.mark.anyio
async def test_copy_file(tmp_path):
    src = tmp_path / "source.txt"
    dst = tmp_path / "copied.txt"
    src.write_text("hello")

    result = await run(operation="copy", source=str(src), dest=str(dst))

    assert result.startswith("[OK]")
    assert src.exists()
    assert dst.read_text() == "hello"


@pytest.mark.anyio
async def test_move_directory(tmp_path):
    src = tmp_path / "sourcedir"
    dst = tmp_path / "moveddir"
    src.mkdir()
    (src / "file.txt").write_text("data")

    result = await run(source=str(src), dest=str(dst))

    assert result.startswith("[OK]")
    assert not src.exists()
    assert (dst / "file.txt").read_text() == "data"


@pytest.mark.anyio
async def test_copy_directory(tmp_path):
    src = tmp_path / "sourcedir"
    dst = tmp_path / "copieddir"
    src.mkdir()
    (src / "file.txt").write_text("data")

    result = await run(operation="copy", source=str(src), dest=str(dst))

    assert result.startswith("[OK]")
    assert src.exists()
    assert (dst / "file.txt").read_text() == "data"


@pytest.mark.anyio
async def test_move_file_dest_is_directory(tmp_path):
    src = tmp_path / "file.txt"
    sub = tmp_path / "subdir"
    sub.mkdir()
    src.write_text("data")

    result = await run(source=str(src), dest=str(sub))

    assert result.startswith("[OK]")
    assert not src.exists()
    assert (sub / "file.txt").read_text() == "data"


@pytest.mark.anyio
async def test_source_not_found(tmp_path):
    src = tmp_path / "nonexistent.txt"
    dst = tmp_path / "dest.txt"

    result = await run(source=str(src), dest=str(dst))

    assert "[ERROR]" in result
    assert "no existe" in result


@pytest.mark.anyio
async def test_missing_params():
    result = await run(source="", dest="")
    assert "[ERROR]" in result

    result = await run(source="/tmp/foo", dest="")
    assert "[ERROR]" in result


@pytest.mark.anyio
async def test_invalid_operation(tmp_path):
    src = tmp_path / "f.txt"
    src.write_text("x")

    result = await run(operation="delete", source=str(src), dest=str(tmp_path / "g.txt"))

    assert "[ERROR]" in result
    assert "Operacion no valida" in result


@pytest.mark.anyio
async def test_move_file_creates_intermediate_dirs(tmp_path):
    src = tmp_path / "source.txt"
    dst = tmp_path / "a" / "b" / "deep.txt"
    src.write_text("data")

    result = await run(source=str(src), dest=str(dst))

    assert result.startswith("[OK]")
    assert dst.read_text() == "data"
