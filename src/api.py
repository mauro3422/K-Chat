"""API facade — capa de abstracción entre web y lógica interna."""

# --- Standard library ---
from collections.abc import Generator
from typing import Any

# --- Core ---
from src.core import (
    chat_stream as _chat_stream,
    get_default_model as _get_default_model,
)
from src.core.orchestrator import generate_session_id as _generate_session_id
from src.core.history import (
    filter_messages_for_ui as _filter_messages_for_ui,
    match_tools_to_msgs as _match_tools_to_msgs,
    rebuild_history as _rebuild_history,
)

# --- LLM ---
from src.llm import (
    PRIORITY as _PRIORITY,
    get_verified_models as _get_verified_models,
)

# --- Memory ---
from src.memory.database import init_db as _init_db
from src.memory.repositories import (
    DebugRepository,
    MessageRecord,
    MessageRepository,
    SavedWidgetRepository,
    SessionRepository,
    ToolCallRepository,
    WidgetStateRepository,
)

# --- Tools ---
from src.tools import TOOL_DEFINITIONS as _TOOL_DEFINITIONS
from src.tools._widget_helpers import sanitize_widget_id  # noqa: F401 — re-exported for web/routers

# --- Background tasks ---
from src.background_tasks import auto_rename_session as _auto_rename_session

# --- Lazy repo registry ---
_repos: dict[str, Any] = {}


def _get_repo(cls: type, name: str) -> Any:
    if name not in _repos:
        _repos[name] = cls()
    return _repos[name]


# === Constants ===

PRIORITY = _PRIORITY
TOOL_DEFINITIONS = _TOOL_DEFINITIONS


# === Session ===

def ensure_session(session_id: str) -> None:
    """Asegura que una sesión exista en la base de datos."""
    return _get_repo(SessionRepository, "session").ensure(session_id)


def rename_session(session_id: str, name: str) -> None:
    """Renombra una sesión existente."""
    return _get_repo(SessionRepository, "session").rename(session_id, name)


def delete_session(session_id: str) -> None:
    """Elimina una sesión y todos sus mensajes y tool calls."""
    return _get_repo(SessionRepository, "session").delete(session_id)


def get_sessions(limit: int = 50) -> list[tuple[Any, ...]]:
    """Retorna la lista de sesiones ordenadas por última actividad."""
    return _get_repo(SessionRepository, "session").get_all(limit)


# === Messages ===

def save_message(*args: Any, **kwargs: Any) -> None:
    """Guarda un mensaje en la base de datos (acepta MessageRecord o args)."""
    repo = _get_repo(MessageRepository, "message")
    if len(args) == 1 and isinstance(args[0], MessageRecord):
        return repo.save_record(args[0])
    return repo.save(*args, **kwargs)


def get_session_messages(session_id: str, limit: int = 200) -> list[tuple[Any, ...]]:
    """Obtiene los mensajes de una sesión ordenados por id."""
    return _get_repo(MessageRepository, "message").get_session_messages(session_id, limit)


# === History ===

def rebuild_history(session_id: str, model: str) -> list[dict[str, Any]]:
    """Reconstruye el historial de mensajes de una sesión para el modelo."""
    return _rebuild_history(session_id, model)


def filter_messages_for_ui(raw_msgs: list[tuple[Any, ...]]) -> list[tuple[Any, ...]]:
    """Filtra mensajes para la UI: excluye tool calls, conserva último assistant."""
    return _filter_messages_for_ui(raw_msgs)


def match_tools_to_msgs(
    msgs: list[tuple[Any, ...]],
    all_tools: list[tuple[Any, ...]],
) -> dict[str, list[Any]]:
    """Asocia cronológicamente tool calls con mensajes assistant de la UI."""
    return _match_tools_to_msgs(msgs, all_tools)


# === Tools ===

def get_tool_history(session_id: str, limit: int = 10) -> list[tuple[Any, ...]]:
    """Obtiene el historial de tool calls de una sesión."""
    return _get_repo(ToolCallRepository, "tool_call").get_history(session_id, limit)


# === Widget state ===

def save_widget_state(session_id: str, widget_id: str, state: str) -> None:
    """Guarda el estado serializado de un widget interactivo."""
    return _get_repo(WidgetStateRepository, "widget").save_state(session_id, widget_id, state)


def get_widget_states(session_id: str) -> dict[str, str]:
    """Obtiene todos los estados de widgets de una sesión."""
    return _get_repo(WidgetStateRepository, "widget").get_states(session_id)


# === Saved widgets ===

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


# === Chat ===

def get_default_model() -> str:
    """Retorna el nombre del modelo por defecto."""
    return _get_default_model()


def get_verified_models() -> list[str]:
    """Retorna la lista de modelos verificados disponibles."""
    return _get_verified_models()


def chat_stream(
    message_user: str,
    history: list[dict[str, Any]],
    model: str | None = None,
    session_id: str | None = None,
    tagged: bool = False,
    debug: dict[str, Any] | None = None,
    phases_output: list[dict[str, Any]] | None = None,
    streaming: bool = True,
) -> Generator[Any, None, None]:
    """Genera tokens de respuesta del modelo para un mensaje de usuario."""
    return _chat_stream(
        message_user, history, model,
        session_id=session_id, tagged=tagged,
        debug=debug, phases_output=phases_output,
        streaming=streaming,
    )


# === Background tasks ===

def auto_rename_session(session_id: str, first_message: str, model: str) -> None:
    """Genera un título automático para la sesión si no tiene nombre."""
    return _auto_rename_session(session_id, first_message, model)


# === Debug ===

def save_debug_info(session_id: str, data: dict[str, Any]) -> None:
    """Guarda información de depuración de una sesión."""
    return _get_repo(DebugRepository, "debug").save_info(session_id, data)


def get_debug_info(session_id: str) -> dict[str, Any]:
    """Obtiene información de depuración de una sesión."""
    return _get_repo(DebugRepository, "debug").get_info(session_id)


# === Database ===

def init_db() -> None:
    """Inicializa la base de datos y ejecuta migraciones pendientes."""
    return _init_db()


def generate_session_id() -> str:
    """Genera un ID único de sesión."""
    return _generate_session_id()
