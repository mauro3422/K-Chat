import logging
from src.llm import chat as llm_chat
from src.memory import rename_session, check_should_rename

logger = logging.getLogger(__name__)

def auto_rename_session(session_id: str, first_message: str, model: str):
    """Genera título automático para la sesión si aún no tiene nombre."""
    if not check_should_rename(session_id):
        return
    prompt = (
        "Genera un título muy corto, directo y descriptivo de 3 a 5 palabras para un chat "
        "que empieza con el siguiente mensaje. No uses comillas, ni introducciones, responde "
        "únicamente con el título en español.\n\n"
        f"Mensaje: {first_message}"
    )
    try:
        r = llm_chat(
            [{"role": "user", "content": prompt}],
            model
        )
        title = (r.message.content or "").strip().replace('"', '').replace("'", "")[:50]
        if title:
            rename_session(session_id, title)
    except Exception as e:
        logger.warning("Error generando título automático de sesión: %s", e)
