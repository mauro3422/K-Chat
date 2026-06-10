from fastapi import APIRouter
from fastapi.responses import JSONResponse
import os

router = APIRouter()

@router.get("/health")
def health():
    checks = {}
    
    # Check database
    try:
        from src.memory.database import get_conn
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
    
    # Check LLM provider
    try:
        api_key = os.environ.get("OPENCODE_ZEN_API_KEY", "")
        checks["llm_provider"] = "configured" if api_key else "not_configured"
    except Exception:
        checks["llm_provider"] = "error"
    
    status = 200 if all(v == "ok" or v == "configured" for v in checks.values()) else 503
    return JSONResponse({"status": "ok" if status == 200 else "degraded", "checks": checks}, status_code=status)
