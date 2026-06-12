import logging
from collections.abc import Callable
from typing import Any

from src.memory.repos import SessionRepository

logger = logging.getLogger(__name__)
_SESSION_REPO = SessionRepository()


def auto_rename_session(
    session_id: str,
    first_message: str,
    model: str,
    chat_fn: Callable[[list[dict[str, Any]], str], Any] | None = None,
) -> None:
    """Generates an automatic title for the session if it has no name yet."""
    if not _SESSION_REPO.check_should_rename(session_id):
        return
    prompt = (
        "Generate a very short, direct, and descriptive title of 3 to 5 words for a chat "
        "that starts with the following message. Do not use quotes or introductions, respond "
        "only with the title.\n\n"
        f"Message: {first_message}"
    )
    try:
        if chat_fn is None:
            from src.llm.client import chat as chat_fn
        r = chat_fn(
            [{"role": "user", "content": prompt}],
            model
        )
        title = (r.message.content or "").strip().replace('"', '').replace("'", "")[:50]
        if title:
            _SESSION_REPO.rename(session_id, title)
    except Exception as e:
        logger.warning("Error generating automatic session title: %s", e)
