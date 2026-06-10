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


def resolve_and_validate_path(path: str) -> tuple[str, str | None]:
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.abspath(os.path.join(CONTEXT_DIR, expanded))
    resolved = os.path.realpath(expanded)
    err = validate_path(path, resolved)
    return resolved, err
