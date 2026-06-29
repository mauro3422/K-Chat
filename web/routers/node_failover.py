"""LAN node failover status endpoint.

Split from ``node.py`` — exposes the auto-promotion state machine snapshot.
URL ``GET /api/node/failover/status`` unchanged.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.routers._node_helpers import _get_coordinator, _get_failover_state

router = APIRouter(prefix="/api/node")


@router.get("/failover/status")
async def failover_status(request: Request) -> JSONResponse:
    coordinator = _get_coordinator(request)
    state = _get_failover_state(request)
    snapshot = state.snapshot()
    snapshot["ok"] = True
    snapshot["node"] = coordinator.snapshot()
    return JSONResponse(snapshot)