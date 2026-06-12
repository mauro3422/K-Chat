import logging
from src.llm.client import chat as llm_chat
from src.memory.repos import SessionRepository

logger = logging.getLogger(__name__)
_SESSION_REPO = SessionRepository()

def auto_rename_session(session_id: str, first_message: str, model: str) -> None:
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
        r = llm_chat(
            [{"role": "user", "content": prompt}],
            model
        )
        title = (r.message.content or "").strip().replace('"', '').replace("'", "")[:50]
        if title:
            _SESSION_REPO.rename(session_id, title)
    except Exception as e:
        logger.warning("Error generating automatic session title: %s", e)
