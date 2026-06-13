"""History operations."""

from typing import Any

from src.core.history import (
    filter_messages_for_ui as _filter_messages_for_ui,
    match_tools_to_msgs as _match_tools_to_msgs,
    rebuild_history as _rebuild_history,
)


def rebuild_history(session_id: str, model: str, message_repo: Any = None) -> list[dict[str, Any]]:
    """Reconstruye el historial de mensajes de una sesión para el modelo."""
    return _rebuild_history(session_id, model, message_repo)


def filter_messages_for_ui(raw_msgs: list) -> list:
    """Filtra mensajes para la UI: excluye tool calls, conserva último assistant."""
    return _filter_messages_for_ui(raw_msgs)


def match_tools_to_msgs(msgs: list, all_tools: list) -> dict:
    """Asocia cronológicamente tool calls con mensajes assistant de la UI."""
    return _match_tools_to_msgs(msgs, all_tools)
