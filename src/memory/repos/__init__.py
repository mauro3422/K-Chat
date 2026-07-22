"""Lightweight facade for repository classes and bundle helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "_BaseRepository",
    "MessageRecord",
    "MessageRepository",
    "SessionRepository",
    "ToolCallRepository",
    "WidgetStateRepository",
    "MemoryIndexRepository",
    "MemoryReceiptRepository",
    "StreamCheckpointRepository",
    "DebugRepository",
    "SavedWidgetRepository",
    "Repositories",
    "get_repos",
]

_LAZY_EXPORTS = {
    "_BaseRepository": ("src.memory.repos.base", "_BaseRepository"),
    "MessageRecord": ("src.memory.repos.message_repository", "MessageRecord"),
    "MessageRepository": ("src.memory.repos.message_repository", "MessageRepository"),
    "SessionRepository": ("src.memory.repos.session_repository", "SessionRepository"),
    "ToolCallRepository": ("src.memory.repos.tool_call_repository", "ToolCallRepository"),
    "WidgetStateRepository": ("src.memory.repos.widget_state_repository", "WidgetStateRepository"),
    "MemoryIndexRepository": ("src.memory.repos.memory_index_repository", "MemoryIndexRepository"),
    "MemoryReceiptRepository": ("src.memory.repos.memory_receipt_repository", "MemoryReceiptRepository"),
    "StreamCheckpointRepository": ("src.memory.repos.stream_checkpoint_repository", "StreamCheckpointRepository"),
    "DebugRepository": ("src.memory.repos.debug_repository", "DebugRepository"),
    "SavedWidgetRepository": ("src.memory.repos.saved_widget_repository", "SavedWidgetRepository"),
    "Repositories": ("src.memory.repos.bundle", "Repositories"),
    "get_repos": ("src.memory.repos.bundle", "get_repos"),
}


def __getattr__(name: str):
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
