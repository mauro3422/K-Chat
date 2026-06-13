"""Widget state and saved widget operations."""

from typing import Any

from src.memory.repos import WidgetStateRepository, SavedWidgetRepository
from src.api.widgets_contract import WidgetOpsDeps
from src.tools._widget_helpers import sanitize_widget_id


def _resolve_widget_deps(
    widget_state_repo: WidgetStateRepository | None = None,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> WidgetOpsDeps:
    if deps is not None:
        return deps
    return WidgetOpsDeps(
        widget_state_repo=widget_state_repo,
        saved_widget_repo=saved_widget_repo,
    )


def save_widget_state(
    session_id: str,
    widget_id: str,
    state: str,
    widget_state_repo: WidgetStateRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> None:
    """Guarda el estado serializado de un widget interactivo."""
    _deps = _resolve_widget_deps(widget_state_repo=widget_state_repo, deps=deps)
    repo = _deps.widget_state_repo if _deps.widget_state_repo is not None else WidgetStateRepository()
    return repo.save_state(session_id, widget_id, state)


def get_widget_states(
    session_id: str,
    widget_state_repo: WidgetStateRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, str]:
    """Obtiene todos los estados de widgets de una sesión."""
    _deps = _resolve_widget_deps(widget_state_repo=widget_state_repo, deps=deps)
    repo = _deps.widget_state_repo if _deps.widget_state_repo is not None else WidgetStateRepository()
    return repo.get_states(session_id)


def db_save_widget(
    session_id: str,
    widget_id: str,
    code: str,
    description: str = "",
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, Any]:
    """Guarda o actualiza un widget oficial en la base de datos."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.save(session_id, widget_id, code, description)


def db_get_widget(
    widget_id: str,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, Any] | None:
    """Retorna la versión activa (más reciente) de un widget."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.get(widget_id)


def db_get_widget_versions(
    widget_id: str,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> list[dict[str, Any]]:
    """Retorna todas las versiones históricas de un widget."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.get_versions(widget_id)


def db_get_widget_by_version(
    widget_id: str,
    version: int,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, Any] | None:
    """Retorna el código de una versión específica de un widget."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.get_by_version(widget_id, version)
