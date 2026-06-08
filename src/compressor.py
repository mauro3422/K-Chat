import logging
from src.llm import chat as llm_chat

logger = logging.getLogger(__name__)

MAX_HISTORY = 40
KEEP_RECENT = 15
MAX_ESTIMATED_TOKENS = 6000


def estimate_tokens(text: str) -> int:
    """Estimación conservadora del número de tokens (1 token aprox. 4 caracteres)."""
    if not text:
        return 0
    return len(text) // 4


def should_compress(history: list) -> bool:
    """Decide si se debe comprimir el historial según la longitud de mensajes o el volumen de tokens."""
    if len(history) > MAX_HISTORY:
        return True
    
    # Calcular los tokens aproximados en todo el historial
    total_tokens = 0
    for msg in history:
        content = msg.get("content") or ""
        reasoning = msg.get("reasoning") or ""
        total_tokens += estimate_tokens(content) + estimate_tokens(reasoning)
        
    return total_tokens > MAX_ESTIMATED_TOKENS


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
