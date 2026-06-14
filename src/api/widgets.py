"""Widget state and saved widget operations."""

from typing import Any

from src.memory.repos import WidgetStateRepository, SavedWidgetRepository
from src.api.widgets_contract import WidgetOpsDeps
from src.api._resolve import resolve_deps


def _resolve_widget_deps(
    widget_state_repo: WidgetStateRepository | None = None,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> WidgetOpsDeps:
    return resolve_deps(deps, WidgetOpsDeps, widget_state_repo=widget_state_repo, saved_widget_repo=saved_widget_repo)


def save_widget_state(
    session_id: str,
    widget_id: str,
    state: str,
    widget_state_repo: WidgetStateRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> None:
    """Save the serialized state of an interactive widget."""
    _deps = _resolve_widget_deps(widget_state_repo=widget_state_repo, deps=deps)
    repo = _deps.widget_state_repo if _deps.widget_state_repo is not None else WidgetStateRepository()
    return repo.save_state(session_id, widget_id, state)


async def get_widget_states(
    session_id: str,
    widget_state_repo: WidgetStateRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, str]:
    """Get all widget states for a session."""
    _deps = _resolve_widget_deps(widget_state_repo=widget_state_repo, deps=deps)
    repo = _deps.widget_state_repo if _deps.widget_state_repo is not None else WidgetStateRepository()
    return await repo.get_states(session_id)


def db_save_widget(
    session_id: str,
    widget_id: str,
    code: str,
    description: str = "",
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, Any]:
    """Save or update an official widget in the database."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.save(session_id, widget_id, code, description)


def db_get_widget(
    widget_id: str,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, Any] | None:
    """Return the active (most recent) version of a widget."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.get(widget_id)


def db_get_widget_versions(
    widget_id: str,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> list[dict[str, Any]]:
    """Return all historical versions of a widget."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.get_versions(widget_id)


def db_get_widget_by_version(
    widget_id: str,
    version: int,
    saved_widget_repo: SavedWidgetRepository | None = None,
    deps: WidgetOpsDeps | None = None,
) -> dict[str, Any] | None:
    """Return the code of a specific widget version."""
    _deps = _resolve_widget_deps(saved_widget_repo=saved_widget_repo, deps=deps)
    repo = _deps.saved_widget_repo if _deps.saved_widget_repo is not None else SavedWidgetRepository()
    return repo.get_by_version(widget_id, version)
