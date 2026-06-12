from pathlib import Path

from src.tools.execute_command import run as execute_command_run
from src.tools.list_files import run as list_files_run


def test_execute_command_runs_shell_command(tmp_path: Path):
    result = execute_command_run(command="printf hola", cwd=str(tmp_path))
    assert "hola" in result


def test_execute_command_blocks_dangerous_command(tmp_path: Path):
    result = execute_command_run(command="rm -rf /", cwd=str(tmp_path))
    assert "[ERROR]" in result
    assert "bloqueado" in result.lower()


def test_list_files_reports_files(tmp_path: Path):
    (tmp_path / "sample.py").write_text("def alpha():\n    return 1\n", encoding="utf-8")
    (tmp_path / "sample.txt").write_text("hello\nworld\n", encoding="utf-8")

    result = list_files_run(path=str(tmp_path), depth=0)

    assert "sample.py" in result
    assert "sample.txt" in result
    assert "Python" in result or "🐍" in result
