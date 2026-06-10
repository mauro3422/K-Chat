import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.api import get_debug_info
from web.logging import get_backend_logs

router = APIRouter()
logger = logging.getLogger(__name__)


def _local_only(request: Request) -> None:
    if os.environ.get("TESTING") or os.environ.get("ENVIRONMENT") == "development":
        return
    host = request.client.host if request.client else "unknown"
    if host in ("127.0.0.1", "::1", "localhost"):
        return
    logger.warning("Debug endpoint access denied from %s", host)
    raise HTTPException(status_code=403, detail="Debug endpoint disabled in production")


@router.get("/sessions/{session_id}/debug", dependencies=[Depends(_local_only)])
def debug_info(session_id: str) -> JSONResponse:
    d = get_debug_info(session_id)
    return JSONResponse(d)


@router.get("/debug/backend-logs", dependencies=[Depends(_local_only)])
def backend_logs() -> JSONResponse:
    return JSONResponse({"logs": get_backend_logs()})
