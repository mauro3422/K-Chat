"""SSE (Server-Sent Events) router — real-time event stream for the web UI."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from web.routers._memory_snapshot import relay_memory_event
from web.services.event_bus import IEventBus, get_event_bus
from web.services.telegram_reflection import get_telegram_reflection_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events")


@router.get("/stream")
async def sse_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint."""
    client_id = f"webui_{uuid.uuid4().hex[:12]}"
    bus: IEventBus = getattr(request.app.state, "event_bus", None) or get_event_bus()

    async def event_generator():
        # Parse Last-Event-ID header for reconnection replay
        last_event_id_raw = request.headers.get("Last-Event-ID", "")
        last_event_id: int | None = None
        if last_event_id_raw and last_event_id_raw.isdigit():
            last_event_id = int(last_event_id_raw)
        async for sse_message in bus.stream(client_id, last_event_id=last_event_id):
            if await request.is_disconnected():
                break
            yield sse_message

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/notify")
async def notify_event(request: Request) -> dict:
    """Receive a notification from internal services (bot, etc.)."""
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}

    event_type = body.get("type", "unknown")
    event_data = body.get("data", {})
    bus: IEventBus = getattr(request.app.state, "event_bus", None) or get_event_bus()
    reflection = getattr(request.app.state, "telegram_reflection_state", None) or get_telegram_reflection_state()
    await relay_memory_event(request, event_type, event_data)
    reflection.record(event_type, event_data if isinstance(event_data, dict) else {}, path="notify", local_published=True)
    bridge = getattr(request.app.state, "node_bridge", None)
    if bridge is not None:
        try:
            result = await bridge.broadcast_event(event_type, event_data)
            reflection.record(
                event_type,
                event_data if isinstance(event_data, dict) else {},
                path="lan",
                local_published=False,
                lan_sent=getattr(result, "sent", 0) if hasattr(result, "sent") else int(result.get("sent", 0)) if isinstance(result, dict) else 0,
                lan_failed=getattr(result, "failed", 0) if hasattr(result, "failed") else int(result.get("failed", 0)) if isinstance(result, dict) else 0,
            )
        except Exception:
            reflection.record(event_type, event_data if isinstance(event_data, dict) else {}, path="lan", last_error="broadcast_failed")
            logger.warning("LAN event broadcast failed for %s", event_type, exc_info=True)
    logger.debug("SSE notify: %s -> %d clients", event_type, len(getattr(bus, "_queues", {})))
    return {"ok": True, "type": event_type}
