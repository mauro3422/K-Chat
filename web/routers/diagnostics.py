"""JSON diagnostics endpoint for the unified node overview."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.services.diagnostics_snapshot import build_diagnostics_snapshot

router = APIRouter(prefix="/api/diagnostics")


@router.get("")
async def diagnostics(request: Request, key_pattern: str = "") -> JSONResponse:
    snapshot = await build_diagnostics_snapshot(request, key_pattern=key_pattern)
    return JSONResponse({"ok": True, **snapshot})
