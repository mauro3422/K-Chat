import os
import pytest

from src.tools.validate_all import DEFINITION, _find_files, run


def test_definition_structure():
    assert DEFINITION["type"] == "function"
    func = DEFINITION["function"]
    assert func["name"] == "validate_all"
    props = func["parameters"]["properties"]
    assert "files" in props
    assert "path" in props
    assert "pattern" in props


@pytest.mark.anyio
async def test_validate_python_valid(tmp_path):
    pyfile = tmp_path / "hello.py"
    pyfile.write_text("x = 1\nprint(x)\n")

    result = await run(files=[str(pyfile)])

    assert "✅ Pasaron: 1" in result
    assert "❌ Fallaron: 0" in result


@pytest.mark.anyio
async def test_validate_python_syntax_error(tmp_path):
    pyfile = tmp_path / "invalid.py"
    pyfile.write_text("if True\n    pass\n")

    result = await run(files=[str(pyfile)])

    assert "❌ Fallaron: 1" in result
    assert "Error de sintaxis" in result


@pytest.mark.anyio
async def test_validate_json_valid(tmp_path):
    jfile = tmp_path / "data.json"
    jfile.write_text('{"a": 1, "b": 2}')

    result = await run(files=[str(jfile)])

    assert "✅ Pasaron: 1" in result
    assert "❌ Fallaron: 0" in result


@pytest.mark.anyio
async def test_validate_json_invalid(tmp_path):
    jfile = tmp_path / "bad.json"
    jfile.write_text('{"a": 1, }')

    result = await run(files=[str(jfile)])

    assert "❌ Fallaron: 1" in result
    assert "JSON invalido" in result


@pytest.mark.anyio
async def test_validate_multiple_files_mixed(tmp_path):
    good = tmp_path / "good.py"
    good.write_text("x = 1\n")
    bad = tmp_path / "bad.py"
    bad.write_text("x =\n")

    result = await run(files=[str(good), str(bad)])

    assert "✅ Pasaron: 1" in result
    assert "❌ Fallaron: 1" in result


@pytest.mark.anyio
async def test_validate_with_path_and_pattern(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    (tmp_path / "b.py").write_text("y = 2\n")
    (tmp_path / "c.txt").write_text("hello\n")

    result = await run(path=str(tmp_path), pattern="*.py")

    assert "✅ Pasaron: 2" in result
    assert "❌ Fallaron: 0" in result


@pytest.mark.anyio
async def test_validate_file_not_found(tmp_path):
    result = await run(files=[str(tmp_path / "nope.py")])

    assert "❌ Fallaron: 1" in result
    assert "Archivo no encontrado" in result


@pytest.mark.anyio
async def test_validate_no_files_and_no_path():
    result = await run()

    assert "[ERROR]" in result
    assert "files" in result or "path" in result


@pytest.mark.anyio
async def test_validate_too_many_files_truncated(tmp_path):
    files = []
    for i in range(25):
        p = tmp_path / f"f{i}.py"
        p.write_text("x = 1\n")
        files.append(str(p))

    result = await run(files=files)

    assert "20 archivos" in result
    assert "✅ Pasaron: 20" in result


@pytest.mark.anyio
async def test_validate_skipped_extension(tmp_path):
    txt = tmp_path / "notes.txt"
    txt.write_text("some text")

    result = await run(files=[str(txt)])

    assert "⏭️" in result or "Omitidos" in result


def test_find_files(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    (tmp_path / "c.txt").write_text("")

    all_files = _find_files(str(tmp_path))
    assert len(all_files) == 3

    py_files = _find_files(str(tmp_path), pattern="*.py")
    assert len(py_files) == 2


@pytest.mark.anyio
async def test_validate_non_existent_directory():
    result = await run(path="/tmp/__nonexistent_dir_xyz__")

    assert "[ERROR]" in result
    assert "no es un directorio" in result
