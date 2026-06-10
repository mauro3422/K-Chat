"""Widget state and saved widget operations."""

from typing import Any

from src.memory.repositories import WidgetStateRepository, SavedWidgetRepository
from src.tools._widget_helpers import sanitize_widget_id  # noqa: F401 — re-exported for web/routers
from src.api._repos import _get_repo


def save_widget_state(session_id: str, widget_id: str, state: str) -> None:
    """Guarda el estado serializado de un widget interactivo."""
    return _get_repo(WidgetStateRepository, "widget").save_state(session_id, widget_id, state)


def get_widget_states(session_id: str) -> dict[str, str]:
    """Obtiene todos los estados de widgets de una sesión."""
    return _get_repo(WidgetStateRepository, "widget").get_states(session_id)


def db_save_widget(
    session_id: str,
    widget_id: str,
    code: str,
    description: str = "",
) -> dict[str, Any]:
    """Guarda o actualiza un widget oficial en la base de datos."""
    return _get_repo(SavedWidgetRepository, "saved_widget").save(session_id, widget_id, code, description)


def db_get_widget(widget_id: str) -> dict[str, Any] | None:
    """Retorna la versión activa (más reciente) de un widget."""
    return _get_repo(SavedWidgetRepository, "saved_widget").get(widget_id)


def db_get_widget_versions(widget_id: str) -> list[dict[str, Any]]:
    """Retorna todas las versiones históricas de un widget."""
    return _get_repo(SavedWidgetRepository, "saved_widget").get_versions(widget_id)


def db_get_widget_by_version(
    widget_id: str,
    version: int,
) -> dict[str, Any] | None:
    """Retorna el código de una versión específica de un widget."""
    return _get_repo(SavedWidgetRepository, "saved_widget").get_by_version(widget_id, version)
