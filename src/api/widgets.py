"""Widget state and saved widget operations."""

from typing import Any

from src.memory.repos import WidgetStateRepository, SavedWidgetRepository
from src.api._widget_helpers import sanitize_widget_id  # noqa: F401 — re-exported for web/routers


def _get_widget_state_repo(repo: WidgetStateRepository | None = None) -> WidgetStateRepository:
    return repo if repo is not None else WidgetStateRepository()


def _get_saved_widget_repo(repo: SavedWidgetRepository | None = None) -> SavedWidgetRepository:
    return repo if repo is not None else SavedWidgetRepository()


def save_widget_state(session_id: str, widget_id: str, state: str, widget_state_repo: WidgetStateRepository | None = None) -> None:
    """Guarda el estado serializado de un widget interactivo."""
    return _get_widget_state_repo(widget_state_repo).save_state(session_id, widget_id, state)


def get_widget_states(session_id: str, widget_state_repo: WidgetStateRepository | None = None) -> dict[str, str]:
    """Obtiene todos los estados de widgets de una sesión."""
    return _get_widget_state_repo(widget_state_repo).get_states(session_id)


def db_save_widget(
    session_id: str,
    widget_id: str,
    code: str,
    description: str = "",
    saved_widget_repo: SavedWidgetRepository | None = None,
) -> dict[str, Any]:
    """Guarda o actualiza un widget oficial en la base de datos."""
    return _get_saved_widget_repo(saved_widget_repo).save(session_id, widget_id, code, description)


def db_get_widget(widget_id: str, saved_widget_repo: SavedWidgetRepository | None = None) -> dict[str, Any] | None:
    """Retorna la versión activa (más reciente) de un widget."""
    return _get_saved_widget_repo(saved_widget_repo).get(widget_id)


def db_get_widget_versions(widget_id: str, saved_widget_repo: SavedWidgetRepository | None = None) -> list[dict[str, Any]]:
    """Retorna todas las versiones históricas de un widget."""
    return _get_saved_widget_repo(saved_widget_repo).get_versions(widget_id)


def db_get_widget_by_version(
    widget_id: str,
    version: int,
    saved_widget_repo: SavedWidgetRepository | None = None,
) -> dict[str, Any] | None:
    """Retorna el código de una versión específica de un widget."""
    return _get_saved_widget_repo(saved_widget_repo).get_by_version(widget_id, version)
