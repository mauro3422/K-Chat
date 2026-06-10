"""Chat and model operations."""

from collections.abc import Generator
from typing import Any

from src.core import chat_stream as _chat_stream, get_default_model as _get_default_model
from src.llm import get_verified_models as _get_verified_models
from src.background_tasks import auto_rename_session as _auto_rename_session


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


def auto_rename_session(session_id: str, first_message: str, model: str) -> None:
    """Genera un título automático para la sesión si no tiene nombre."""
    return _auto_rename_session(session_id, first_message, model)
