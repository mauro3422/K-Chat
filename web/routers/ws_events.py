"""WebSocket router — receives streaming tokens from the bot and
publishes them to the EventBus for SSE distribution to the web UI.

Endpoints:
- ``ws://host/api/ws/events`` — bot connects here and sends token events

Auto-discovered by ``app_factory.register_routers()``.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket

from web.services.event_bus import get_event_bus

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/api/ws/events")
async def ws_event_stream(websocket: WebSocket) -> None:
    """WebSocket endpoint for the bot to stream live tokens.

    Expected message format (JSON)::

        {"type": "token:reasoning", "data": {"session_id": "...", "content": "..."}}
        {"type": "token:content", "data": {"session_id": "...", "content": "..."}}
        {"type": "tool_call", "data": {"session_id": "...", "tool_name": "...", "status": "..."}}
        {"type": "new_message", "data": {"session_id": "...", ...}}

    Each message is published to the EventBus and fanned out to all SSE clients.
    """
    await websocket.accept()
    bus = getattr(websocket.app.state, 'event_bus', None) or get_event_bus()
    logger.info("WS bot connected")
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("WS: invalid JSON from bot")
                continue

            event_type = msg.get("type", "unknown")
            event_data = msg.get("data", {})
            await bus.publish(event_type, event_data)
            logger.debug("WS event: %s → session %s", event_type, event_data.get("session_id", "?"))
    except Exception:
        logger.info("WS bot disconnected")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
