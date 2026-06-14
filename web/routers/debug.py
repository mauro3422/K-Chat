import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.memory.repos import get_repos
from web.logging_handler import get_backend_logs

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/rate-limits")
async def rate_limits(request: Request) -> dict:
    _local_only(request)
    from src.llm.rate_limit_state import get_rate_limit_store
    return get_rate_limit_store().summary()


def _local_only(request: Request) -> None:
    if os.getenv("TESTING") == "true":
        return
    host = request.client.host if request.client else "unknown"
    if host in ("127.0.0.1", "::1", "localhost"):
        return
    logger.warning("Debug endpoint access denied from %s", host)
    raise HTTPException(status_code=403, detail="Debug endpoint disabled in production")


@router.get("/sessions/{session_id}/debug", dependencies=[Depends(_local_only)])
async def debug_info(session_id: str) -> JSONResponse:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    d = await repos.debug.get_info(session_id)
    return JSONResponse(d)


@router.get("/debug/backend-logs", dependencies=[Depends(_local_only)])
def backend_logs() -> JSONResponse:
    return JSONResponse({"logs": get_backend_logs()})
