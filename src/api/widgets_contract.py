"""Contracts for widget operations."""

from __future__ import annotations

from dataclasses import dataclass

from src.memory.repos import SavedWidgetRepository, WidgetStateRepository


@dataclass(slots=True)
class WidgetOpsDeps:
    """Optional dependency bundle for widget state and saved-widget operations."""

    widget_state_repo: WidgetStateRepository | None = None
    saved_widget_repo: SavedWidgetRepository | None = None
