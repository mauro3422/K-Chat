import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

MAX_HISTORY = 40
KEEP_RECENT = 15
MAX_ESTIMATED_TOKENS = 6000


def estimate_tokens(text: str) -> int:
    """Estimación conservadora del número de tokens (1 token aprox. 4 caracteres)."""
    if not text:
        return 0
    return len(text) // 4


def should_compress(history: list[Any]) -> bool:
    """Decide si se debe comprimir el historial según la longitud de mensajes o el volumen de tokens."""
    if len(history) > MAX_HISTORY:
        return True
    
    # Calcular los tokens aproximados en todo el historial
    total_tokens = 0
    for msg in history:
        # Compatibility: handle both dicts and HistoryMessage objects
        content = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else "") or ""
        reasoning = getattr(msg, "reasoning", "") or (msg.get("reasoning") if isinstance(msg, dict) else "")
        total_tokens += estimate_tokens(str(content)) + estimate_tokens(str(reasoning))
        
    return total_tokens > MAX_ESTIMATED_TOKENS


async def compress_history(
    history: list[Any],
    model: str,
    chat_fn: Callable[[list[dict[str, Any]], str], Any] | None = None,
) -> None:
    keep = KEEP_RECENT
    to_compress = history[1:-keep]
    if not to_compress:
        return
    recent = history[-keep:]
    
    lines = []
    for m in to_compress:
        role = getattr(m, "role", None) or (m.get("role") if isinstance(m, dict) else "unknown")
        content = getattr(m, "content", None) or (m.get("content") if isinstance(m, dict) else "") or ""
        lines.append(f"{role}: {str(content)[:300]}")
        
    text = "\n".join(lines)
    try:
        if chat_fn is None:
            from src.llm.client import chat as chat_fn
        r = await chat_fn(
            [{"role": "user", "content": f"Summarize this conversation in 2-3 lines, key facts only:\n\n{text}"}],
            model
        )
        summary = (r.message.content or "").strip()
        if summary:
            history[:] = [history[0], {"role": "system", "content": f"[Resumen: {summary}]"}] + recent
    except Exception as e:
        logger.warning("compress_history failed (model=%s, msgs=%d): %s", model, len(history), e)
