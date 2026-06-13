import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def _get_session_repo(repo=None):
    if repo is not None:
        return repo
    from src.memory.repos import SessionRepository
    return SessionRepository()


def auto_rename_session(
    session_id: str,
    message: str,
    model: str,
    chat_fn: Callable[..., Any] | None = None,
    session_repo=None,
) -> None:
    """Generates an automatic title for the session if it has no name yet."""
    repo = _get_session_repo(session_repo)
    if not repo.check_should_rename(session_id):
        return
    prompt = (
        "Generate a very short, direct, and descriptive title of 3 to 5 words for a chat "
        "that starts with the following message. Do not use quotes or introductions, respond "
        "only with the title.\n\n"
        f"Message: {message}"
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
            repo.rename(session_id, title)
    except Exception as e:
        logger.warning("Error generating automatic session title: %s", e)
