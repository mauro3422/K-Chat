from fastapi import APIRouter
from fastapi.responses import JSONResponse

from src.api.repos import get_conn
from src.config_loader import load_config

router = APIRouter()

@router.get("/health")
async def health():
    checks = {}

    try:
        conn = await get_conn()
        await conn.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"

    # Check LLM provider
    try:
        api_key = load_config().opencode_zen_api_key
        checks["llm_provider"] = "configured" if api_key else "not_configured"
    except Exception:
        checks["llm_provider"] = "error"
    
    status = 200 if all(v == "ok" or v == "configured" for v in checks.values()) else 503
    return JSONResponse({"status": "ok" if status == 200 else "degraded", "checks": checks}, status_code=status)
