import logging
from src.llm import chat as llm_chat

logger = logging.getLogger(__name__)

MAX_HISTORY = 40
KEEP_RECENT = 15


def compress_history(history: list, model: str) -> None:
    keep = KEEP_RECENT
    to_compress = history[1:-keep]
    if not to_compress:
        return
    recent = history[-keep:]
    text = "\n".join(
        f"{m['role']}: {(m.get('content') or '')[:300]}" for m in to_compress
    )
    try:
        r = llm_chat(
            [{"role": "user", "content": f"Resumi esta conversacion en 2-3 lineas, solo hechos clave:\n\n{text}"}],
            model
        )
        summary = (r.message.content or "").strip()
        if summary:
            history[:] = [history[0], {"role": "system", "content": f"[Resumen: {summary}]"}] + recent
    except Exception as e:
        logger.warning("compress_history falló: %s", e)
