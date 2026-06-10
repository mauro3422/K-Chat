import logging
from src.memory.repos import MessageRepository
from src.core.history_parser import _parse_rows, _sanitize_messages
from src.core.history_rebuilder import rebuild_history
from src.core.history_ui import filter_messages_for_ui, match_tools_to_msgs

logger = logging.getLogger(__name__)

_repo: MessageRepository | None = None


def _get_repo() -> MessageRepository:
    global _repo
    if _repo is None:
        _repo = MessageRepository()
    return _repo

# Re-export for backwards compatibility
__all__ = [
    "_parse_rows",
    "_sanitize_messages",
    "rebuild_history",
    "filter_messages_for_ui",
    "match_tools_to_msgs",
]
