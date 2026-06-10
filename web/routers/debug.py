import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.api import get_debug_info
from web.logging import get_backend_logs

router = APIRouter()


def _local_only(request: Request) -> None:
    if os.environ.get("TESTING"):
        return
    host = request.client.host if request.client else "unknown"
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/sessions/{session_id}/debug", dependencies=[Depends(_local_only)])
def debug_info(session_id: str) -> JSONResponse:
    d = get_debug_info(session_id)
    return JSONResponse(d)


@router.get("/debug/backend-logs", dependencies=[Depends(_local_only)])
def backend_logs() -> JSONResponse:
    return JSONResponse({"logs": get_backend_logs()})
