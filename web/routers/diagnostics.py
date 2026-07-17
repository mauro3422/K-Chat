"""JSON diagnostics endpoint for the unified node overview."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.coordination.lan_bridge import NodeLanBridge
from web.services.diagnostics_snapshot import build_diagnostics_snapshot
from web.services.peer_cluster_snapshot import peer_urls_from_bridge

router = APIRouter(prefix="/api/diagnostics")


def _get_bridge(request: Request) -> NodeLanBridge | None:
    bridge = getattr(request.app.state, "node_bridge", None)
    if bridge is not None:
        return bridge
    coordinator = getattr(request.app.state, "node_coordinator", None)
    cfg = getattr(request.app.state, "config", None)
    if coordinator is None:
        return None
    bridge = NodeLanBridge(config=cfg, coordinator=coordinator)
    request.app.state.node_bridge = bridge
    return bridge


@router.get("")
async def diagnostics(request: Request, key_pattern: str = "") -> JSONResponse:
    snapshot = await build_diagnostics_snapshot(request, key_pattern=key_pattern)
    return JSONResponse({"ok": True, **snapshot})


@router.get("/peer")
async def peer_diagnostics(request: Request, peer_url: str, kind: str = "diagnostics", key_pattern: str = "") -> JSONResponse:
    bridge = _get_bridge(request)
    if bridge is None:
        return JSONResponse({"ok": False, "error": "node bridge not available"}, status_code=503)
    peer = peer_url.strip().rstrip("/")
    if peer not in peer_urls_from_bridge(bridge):
        return JSONResponse({"ok": False, "error": "peer not configured"}, status_code=404)

    if kind == "state":
        result = await bridge.request_peer_state(peer=peer)
    elif kind == "memory":
        result = await bridge.request_memory_snapshot(key_pattern=key_pattern, peer=peer)
    else:
        result = await bridge.request_peer_diagnostics(peer=peer, key_pattern=key_pattern)

    if not result.get("ok"):
        return JSONResponse(result, status_code=502)
    return JSONResponse(result)
