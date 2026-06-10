import os

from src.paths import CONTEXT_DIR


def validate_path(path: str, expanded: str) -> str | None:
    resolved = os.path.realpath(expanded)
    project_root = os.path.realpath(CONTEXT_DIR)
    home = os.path.realpath(os.path.expanduser("~"))

    for base in (project_root, home, "/tmp"):
        base_resolved = os.path.realpath(base)
        if os.path.commonpath([resolved, base_resolved]) == base_resolved:
            return None

    return f"[ERROR] Access denied. The path '{path}' is outside the allowed directories."
