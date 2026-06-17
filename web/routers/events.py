"""SSE (Server-Sent Events) router — real-time event stream for the web UI.

Endpoints:
- ``GET /api/events/stream`` — SSE stream (web UI connects here)
- ``POST /api/events/notify`` — internal endpoint for services (bot, etc.)
  to broadcast events (e.g. "new Telegram message")

Auto-discovered by ``app_factory.register_routers()``.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from web.services.event_bus import IEventBus, get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/events")


@router.get("/stream")
async def sse_stream(request: Request) -> StreamingResponse:
    """Server-Sent Events endpoint.

    The client connects here and receives events as they happen.
    """
    client_id = f"webui_{uuid.uuid4().hex[:12]}"
    bus: IEventBus = getattr(request.app.state, 'event_bus', None) or get_event_bus()

    async def event_generator():
        async for sse_message in bus.stream(client_id):
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
    """Receive a notification from internal services (bot, etc.).

    Expected JSON body::

        {"type": "new_message", "data": {"session_id": "...", ...}}
    """
    try:
        body = await request.json()
    except Exception:
        return {"ok": False, "error": "invalid JSON"}

    event_type = body.get("type", "unknown")
    event_data = body.get("data", {})
    bus: IEventBus = getattr(request.app.state, 'event_bus', None) or get_event_bus()
    await bus.publish(event_type, event_data)
    logger.info("SSE notify: %s → %d clients", event_type, len(bus._queues))
    return {"ok": True, "type": event_type}
