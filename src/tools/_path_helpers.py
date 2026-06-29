import os

from src.paths import CONTEXT_DIR


def _normalise_for_boundary_check(path: str) -> str:
    normalised = os.path.normcase(os.path.normpath(path)).replace("\\", "/")
    if len(normalised) > 1:
        normalised = normalised.rstrip("/")
    return normalised


def _is_within_boundary(path: str, base: str) -> bool:
    normalised_path = _normalise_for_boundary_check(path)
    normalised_base = _normalise_for_boundary_check(base)
    if normalised_base in {"", "/", "."}:
        return False
    return normalised_path == normalised_base or normalised_path.startswith(normalised_base + "/")


def validate_path(path: str, expanded: str) -> str | None:
    resolved = os.path.realpath(expanded)
    project_root = os.path.realpath(CONTEXT_DIR)
    home = os.path.realpath(os.path.expanduser("~"))

    for base in (project_root, home, "/tmp"):
        base_resolved = os.path.realpath(base)
        if _is_within_boundary(resolved, base_resolved):
            return None

    return f"[ERROR] Access denied. The path '{path}' is outside the allowed directories."


def resolve_and_validate_path(path: str) -> tuple[str, str | None]:
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        expanded = os.path.abspath(os.path.join(CONTEXT_DIR, expanded))
    resolved = os.path.realpath(expanded)
    err = validate_path(path, resolved)
    return resolved, err
