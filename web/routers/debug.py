import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.memory import get_debug_info

router = APIRouter()

# Buffer circular para logs recientes del backend
_backend_log_buffer = []
_max_backend_logs = 100

class BackendLogHandler(logging.Handler):
    def emit(self, record):
        global _backend_log_buffer
        try:
            log_entry = {
                "ts": record.created,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage()
            }
            _backend_log_buffer.append(log_entry)
            if len(_backend_log_buffer) > _max_backend_logs:
                _backend_log_buffer = _backend_log_buffer[-_max_backend_logs:]
        except Exception:
            pass

# Registrar el handler para capturar logs del backend
_backend_handler = BackendLogHandler()
logging.getLogger().addHandler(_backend_handler)
logging.getLogger("src.llm").setLevel(logging.INFO)
logging.getLogger("web.routers.chat").setLevel(logging.INFO)


@router.get("/sessions/{session_id}/debug")
async def debug_info(session_id: str):
    d = get_debug_info(session_id)
    return JSONResponse(d)


@router.get("/debug/backend-logs")
async def backend_logs():
    """Devuelve los logs recientes del backend."""
    return JSONResponse({"logs": list(_backend_log_buffer)})
