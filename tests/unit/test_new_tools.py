import pytest
from unittest.mock import AsyncMock
from pathlib import Path
import sys

from src.tools.execute_command import run as execute_command_run
from src.tools.list_files import run as list_files_run


@pytest.mark.anyio
async def test_execute_command_runs_shell_command(tmp_path: Path):
    result = execute_command_run(command="echo hola", cwd=str(tmp_path))
    assert "hola" in result


@pytest.mark.anyio
async def test_execute_command_blocks_dangerous_command(tmp_path: Path):
    result = execute_command_run(command="rm -rf /", cwd=str(tmp_path))
    assert "[ERROR]" in result
    assert "bloqueado" in result.lower()


@pytest.mark.anyio
async def test_execute_command_rejects_outside_cwd():
    result = execute_command_run(command="printf hola", cwd="/etc")
    assert "[ERROR]" in result
    assert "outside the allowed directories" in result


@pytest.mark.anyio
async def test_execute_command_truncates_large_output(tmp_path: Path):
    result = execute_command_run(
        command=f'"{sys.executable}" -c "print(\'x\' * 40050)"',
        cwd=str(tmp_path),
    )
    assert "...[truncado" in result or "truncado" in result.lower()
    assert len(result) <= 30050


@pytest.mark.anyio
async def test_list_files_reports_files(tmp_path: Path):
    (tmp_path / "sample.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "sample.txt").write_text("hello\nworld\n", encoding="utf-8")

    result = await list_files_run(path=str(tmp_path), depth=0)

    assert "sample.py" in result
    assert "sample.txt" in result
    assert "Python" in result or "🐍" in result


@pytest.mark.anyio
async def test_list_files_rejects_outside_path():
    result = await list_files_run(path="/etc", depth=0)
    assert "[ERROR]" in result
    assert "outside the allowed directories" in result


@pytest.mark.anyio
async def test_list_files_truncates_large_directory(tmp_path: Path):
    for i in range(210):
        (tmp_path / f"file_{i:03d}.txt").write_text("x\n", encoding="utf-8")

    result = await list_files_run(path=str(tmp_path), depth=0)

    assert "limite de 200 archivos alcanzado" in result
