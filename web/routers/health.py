from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.config_loader import DEFAULT_CONFIG
from src.memory.connection_pool import get_conn

router = APIRouter()

@router.get("/health")
def health():
    checks = {}

    try:
        conn = get_conn()
        conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check LLM provider
    try:
        api_key = DEFAULT_CONFIG.opencode_zen_api_key
        checks["llm_provider"] = "configured" if api_key else "not_configured"
    except Exception:
        checks["llm_provider"] = "error"
    
    status = 200 if all(v == "ok" or v == "configured" for v in checks.values()) else 503
    return JSONResponse({"status": "ok" if status == 200 else "degraded", "checks": checks}, status_code=status)
