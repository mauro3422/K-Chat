"""API facade — capa de abstracción entre web y lógica interna."""

from src.api.session import ensure_session, rename_session, delete_session, get_sessions
from src.api.messages import save_message, get_session_messages
from src.api.history import rebuild_history, filter_messages_for_ui, match_tools_to_msgs
from src.api.tools import get_tool_history
from src.api.widgets import (
    save_widget_state, get_widget_states, db_save_widget,
    db_get_widget, db_get_widget_versions, db_get_widget_by_version,
    sanitize_widget_id,
)
from src.api.chat import get_default_model, get_verified_models, chat_stream, auto_rename_session
from src.api.debug import save_debug_info, get_debug_info
from src.api.database import init_db, generate_session_id
from src.api._repos import _get_repo  # noqa: F401 — may be needed by consumers

# Constants
from src.llm import PRIORITY
from src.tools import TOOL_DEFINITIONS

__all__ = [
    "ensure_session", "rename_session", "delete_session", "get_sessions",
    "save_message", "get_session_messages",
    "rebuild_history", "filter_messages_for_ui", "match_tools_to_msgs",
    "get_tool_history",
    "save_widget_state", "get_widget_states", "db_save_widget",
    "db_get_widget", "db_get_widget_versions", "db_get_widget_by_version",
    "sanitize_widget_id",
    "get_default_model", "get_verified_models", "chat_stream", "auto_rename_session",
    "save_debug_info", "get_debug_info",
    "init_db", "generate_session_id",
    "PRIORITY", "TOOL_DEFINITIONS",
]
