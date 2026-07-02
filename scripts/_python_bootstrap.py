"""Bootstrap helpers for local Kairos maintenance scripts."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def ensure_repo_python(script_file: str, *, command_name: str) -> None:
    """Re-run the current script with the repo virtualenv Python when needed."""
    script_path = Path(script_file).resolve()
    root = _project_root(script_path)
    python_path = _find_repo_python(root)
    if python_path is None:
        _ensure_required_modules(root, command_name, ("fastembed", "sqlite_vec"), allow_system=True)
        return
    if not _same_executable(Path(sys.executable), python_path):
        _reexec(python_path, script_path, root)
    _ensure_required_modules(root, command_name, ("fastembed", "sqlite_vec"), allow_system=False)


def _project_root(script_path: Path) -> Path:
    root = script_path.parents[1]
    if not (root / "requirements.txt").exists() or not (root / "src").is_dir():
        raise SystemExit(
            "Kairos project root not found. Run this command from the Kairos repo, "
            "for example: cd C:\\Dev\\Kairos"
        )
    return root


def _repo_python_candidates(root: Path) -> list[Path]:
    return [
        root / "venv" / "Scripts" / "python.exe",
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "bin" / "python",
        root / ".venv" / "bin" / "python",
    ]


def _find_repo_python(root: Path) -> Path | None:
    for candidate in _repo_python_candidates(root):
        if candidate.exists():
            return candidate
    return None


def _same_executable(left: Path, right: Path) -> bool:
    try:
        left_resolved = left.resolve()
    except OSError:
        left_resolved = left
    try:
        right_resolved = right.resolve()
    except OSError:
        right_resolved = right
    if os.name == "nt":
        return os.path.normcase(str(left_resolved)) == os.path.normcase(str(right_resolved))
    return left_resolved == right_resolved


def _reexec(python_path: Path, script_path: Path, root: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root) if not env.get("PYTHONPATH") else str(root) + os.pathsep + env["PYTHONPATH"]
    if os.name == "nt":
        result = subprocess.run([str(python_path), str(script_path), *sys.argv[1:]], env=env)
        raise SystemExit(result.returncode)
    os.execve(str(python_path), [str(python_path), str(script_path), *sys.argv[1:]], env)


def _ensure_required_modules(
    root: Path,
    command_name: str,
    modules: tuple[str, ...],
    *,
    allow_system: bool,
) -> None:
    missing = [module for module in modules if importlib.util.find_spec(module) is None]
    if missing:
        if allow_system:
            raise SystemExit(_missing_env_message(root, command_name, missing))
        raise SystemExit(_missing_dependency_message(root, command_name, missing))


def _missing_env_message(root: Path, command_name: str, missing: list[str] | None = None) -> str:
    if os.name == "nt":
        fix = (
            "  py -3 -m venv .venv\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        )
        retry = f"  .\\.venv\\Scripts\\python.exe {command_name}"
    else:
        fix = (
            "  python3 -m venv .venv\n"
            "  .venv/bin/python -m pip install -r requirements.txt"
        )
        retry = f"  .venv/bin/python {command_name}"
    return (
        "Kairos Python environment not found.\n"
        f"Repo: {root}\n"
        "Expected a repo venv or the current Python with required packages.\n"
        "Repo venv paths: venv/Scripts/python.exe, .venv/Scripts/python.exe, "
        "venv/bin/python, .venv/bin/python\n"
        f"Current Python: {sys.executable}\n"
        f"{'Missing: ' + ', '.join(missing) + chr(10) if missing else ''}"
        "Fix:\n"
        f"{fix}\n"
        f"Retry:\n"
        f"{retry}"
    )


def _missing_dependency_message(root: Path, command_name: str, missing: list[str]) -> str:
    if os.name == "nt":
        fix = "  .\\.venv\\Scripts\\python.exe -m pip install -r requirements.txt"
        retry = f"  .\\.venv\\Scripts\\python.exe {command_name}"
    else:
        fix = "  .venv/bin/python -m pip install -r requirements.txt"
        retry = f"  .venv/bin/python {command_name}"
    return (
        "Kairos Python environment is missing required packages.\n"
        f"Repo: {root}\n"
        f"Missing: {', '.join(missing)}\n"
        "Fix:\n"
        f"{fix}\n"
        f"Retry:\n"
        f"{retry}"
    )
