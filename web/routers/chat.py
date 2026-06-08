import json
import logging
from datetime import datetime

from fastapi import APIRouter, Form, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse

from src.core import chat_stream, build_system_prompt, get_default_model
from src.background_tasks import auto_rename_session
from src.memory import ensure_session, get_session_messages, save_message as db_save_message, save_debug_info

router = APIRouter()
logger = logging.getLogger(__name__)


def rebuild_history(session_id: str, model: str) -> list:
    rows = get_session_messages(session_id)
    history = [build_system_prompt(model)]
    for role, content, *_ in rows:
        if role != "system":
            history.append({"role": role, "content": content})
    return history


class StreamError(Exception):
    def __init__(self, message, error_type="unknown"):
        self.message = message
        self.error_type = error_type
        super().__init__(message)


@router.post("/chat/{session_id}")
async def chat(session_id: str, background_tasks: BackgroundTasks, message: str = Form(...), model: str = ""):
    if not session_id or not session_id.strip():
        raise HTTPException(400, "session_id inválido")
    if not message.strip():
        return ""
    if not model:
        model = get_default_model()

    ensure_session(session_id)
    try:
        history = rebuild_history(session_id, model)
    except Exception as e:
        logger.error("Error reconstruyendo historial para %s: %s", session_id, e)
        raise HTTPException(500, "Error al cargar historial")

    def generate():
        full_reasoning = ""
        full_content = ""
        debug_info = {}
        phases_output = []
        
        logger.info("Iniciando chat para session %s con modelo %s", session_id, model)
        
        try:
            for tipo, token in chat_stream(message, history, model, session_id=session_id, tagged=True, debug=debug_info, phases_output=phases_output):
                if tipo == "reasoning":
                    full_reasoning += token
                elif tipo == "content":
                    full_content += token
                yield json.dumps({"t": tipo, "d": token}) + "\n"
        except Exception as e:
            error_msg = str(e)
            error_type = "unknown"
            
            if "rate limit" in error_msg.lower():
                error_type = "rate_limit"
                error_msg = "Límite de tasa alcanzado. Espera un momento antes de reintentar."
            elif "timeout" in error_msg.lower():
                error_type = "timeout"
                error_msg = "El modelo tardó demasiado en responder."
            elif "connection" in error_msg.lower() or "network" in error_msg.lower():
                error_type = "network"
                error_msg = "Error de conexión con el modelo."
            elif "model" in error_msg.lower() or "api" in error_msg.lower():
                error_type = "model"
                error_msg = f"Error del modelo: {error_msg}"
            
            logger.error("Error en stream para %s: [%s] %s", session_id, error_type, error_msg)
            yield json.dumps({"t": "error", "d": {"type": error_type, "message": error_msg}}) + "\n"
            return
        
        # Verificar si la respuesta estuvo vacía
        if not full_content and not full_reasoning:
            logger.warning("Respuesta vacía para session %s con modelo %s", session_id, model)
            yield json.dumps({"t": "error", "d": {"type": "empty_response", "message": "El modelo no generó contenido"}}) + "\n"
            return
        
        logger.info("Chat completado para session %s: %d chars content, %d chars reasoning", session_id, len(full_content), len(full_reasoning))
        
        phases_json = json.dumps(phases_output, ensure_ascii=False)
        db_save_message(session_id, "user", message, model)
        pt = debug_info.get("prompt_tokens", 0)
        ct = debug_info.get("completion_tokens", 0)
        tt = debug_info.get("total_tokens", 0)
        db_save_message(
            session_id, "assistant", full_content, model,
            reasoning=full_reasoning, phases=phases_json,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=tt
        )
        if not debug_info.get("phases"):
            debug_info["phases"] = phases_json
        save_debug_info(session_id, debug_info)
        background_tasks.add_task(auto_rename_session, session_id, message, model)

    return StreamingResponse(generate(), media_type="application/x-ndjson")
