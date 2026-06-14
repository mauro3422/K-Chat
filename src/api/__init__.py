"""Public API for K-Chat — the only interface entry points should use.

Entry (web/, cli.py, channels/) → API (src.api) → Core (src.core/)
"""

# ── Session operations ────────────────────────────────────────────────────
from src.api.session import (
    ensure_session,
    rename_session,
    delete_session,
    get_sessions,
)

# ── Debug operations ──────────────────────────────────────────────────────
from src.api.debug import (
    save_debug_info,
    get_debug_info,
    append_asr_telemetry,
)

# ── Message operations ────────────────────────────────────────────────────
from src.api.messages import (
    save_message_record,
    get_session_messages,
)

# ── Tool history & widget helpers ──────────────────────────────────────────
from src.api.tools import (
    get_tool_history,
    sanitize_widget_id,
)

# ── Widget operations ─────────────────────────────────────────────────────
from src.api.widgets import (
    save_widget_state,
    get_widget_states,
    db_save_widget,
    db_get_widget,
    db_get_widget_versions,
    db_get_widget_by_version,
)

# ── Orchestrator ───────────────────────────────────────────────────────────
from src.api.orchestrator import (
    chat_stream,
    generate_session_id,
    OrchestratorDeps,
    rebuild_history,
    HistoryRebuildDeps,
    filter_messages_for_ui,
    match_tools_to_msgs,
    HistoryService,
    LLMService,
    ToolExecutionService,
    TelemetryService,
)

# ── LLM / Model discovery ──────────────────────────────────────────────────
from src.api.llm_client import (
    get_default_model,
    get_verified_models,
    get_verified_models_safe,
    get_model_registry,
    ensure_registry_refreshed,
    get_rate_limit_store,
    PRIORITY,
    FALLBACK_MODEL,
    llm_chat_stream,
    llm_chat,
)

# ── Repositories & data ──────────────────────────────────────────────────
from src.api.repos import (
    get_repos,
    Repositories,
    MessageRecord,
    SessionRepository,
    DebugRepository,
    init_db,
    DebugInfo,
    get_conn,
)

# ── Context builder ────────────────────────────────────────────────────────
from src.api.context import (
    build_system_prompt,
)

# ── Background tasks ───────────────────────────────────────────────────────
from src.api.background import (
    auto_rename_session,
)

# ── Chat journal ───────────────────────────────────────────────────────────
from src.api.journal import (
    log_turn,
)

# ── Skills ─────────────────────────────────────────────────────────────────
from src.api.skills import (
    SkillRegistry,
)

# ── Exceptions ─────────────────────────────────────────────────────────────
from src.api.exceptions import ServiceException

__all__ = [
    # session
    "ensure_session", "rename_session", "delete_session", "get_sessions",
    # debug
    "save_debug_info", "get_debug_info", "append_asr_telemetry",
    # messages
    "save_message_record", "get_session_messages",
    # tools
    "get_tool_history", "sanitize_widget_id",
    # widgets
    "save_widget_state", "get_widget_states",
    "db_save_widget", "db_get_widget", "db_get_widget_versions", "db_get_widget_by_version",
    # orchestrator
    "chat_stream", "generate_session_id", "OrchestratorDeps",
    "rebuild_history", "HistoryRebuildDeps",
    "filter_messages_for_ui", "match_tools_to_msgs",
    "HistoryService", "LLMService", "ToolExecutionService", "TelemetryService",
    # llm
    "get_default_model", "get_verified_models", "get_verified_models_safe",
    "get_model_registry", "ensure_registry_refreshed", "get_rate_limit_store",
    "PRIORITY", "FALLBACK_MODEL", "llm_chat_stream", "llm_chat",
    # repos & data
    "get_repos", "Repositories", "MessageRecord", "SessionRepository",
    "DebugRepository", "init_db", "DebugInfo", "get_conn",
    # context
    "build_system_prompt",
    # background
    "auto_rename_session",
    # journal
    "log_turn",
    # skills
    "SkillRegistry",
    # exceptions
    "ServiceException",
]
