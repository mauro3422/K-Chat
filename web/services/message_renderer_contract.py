"""Contracts for server-side message rendering."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any
from src.api.repos import Repositories


@dataclass(slots=True)
class MessageRenderDeps:
    """Optional dependency bundle for session message rendering."""

    get_session_messages_fn: Callable[[str], list] | None = None
    filter_messages_fn: Callable[[list], list] | None = None
    get_tool_history_fn: Callable[[str, int], list] | None = None
    match_tools_fn: Callable[[list, list], dict[str, list[Any]]] | None = None
    get_widget_states_fn: Callable[[str], dict[str, Any]] | None = None
    extract_inline_widget_states_fn: Callable[[list], dict[str, str]] | None = None
    repos: Repositories | None = None
