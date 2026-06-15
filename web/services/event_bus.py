"""Event bus — in-memory pub/sub for Server-Sent Events (SSE).

Lego block: no framework imports, pure asyncio, injectable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

logger = logging.getLogger(__name__)


class EventBus:
    """Simple in-memory pub/sub event bus.

    Usage::

        bus = EventBus()
        # Client subscribes
        async for event in bus.subscribe("client_123"):
            ...  # yields dicts like {"type": "new_message", "data": {...}}

        # Publisher
        await bus.publish("new_message", {"session_id": "...", "content": "..."})
    """

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, client_id: str) -> asyncio.Queue:
        """Register a client and return its event queue."""
        async with self._lock:
            if client_id not in self._queues:
                self._queues[client_id] = asyncio.Queue(maxsize=100)
            return self._queues[client_id]

    async def unsubscribe(self, client_id: str) -> None:
        """Remove a client."""
        async with self._lock:
            self._queues.pop(client_id, None)

    async def publish(self, event_type: str, data: Any = None) -> None:
        """Send an event to ALL connected clients."""
        payload = {"type": event_type, "data": data}
        async with self._lock:
            dead: list[str] = []
            for cid, q in self._queues.items():
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(cid)
                    logger.warning("EventBus: client %s queue full, dropping", cid)
            for cid in dead:
                self._queues.pop(cid, None)

    async def stream(self, client_id: str) -> AsyncGenerator[str, None]:
        """Async generator that yields SSE-formatted strings with event IDs.

        The ``id:`` field lets the browser send ``Last-Event-ID`` on reconnect,
        enabling the server to resume from where it left off.
        Use this in the FastAPI StreamingResponse.
        """
        import json as _json
        q = await self.subscribe(client_id)
        seq = 0
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30)
                    seq += 1
                    yield f"id: {seq}\ndata: {_json.dumps(event, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {_json.dumps({'type': 'ping'})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await self.unsubscribe(client_id)


# Module-level singleton (lazy, created on first use)
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """Get or create the global EventBus singleton."""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
