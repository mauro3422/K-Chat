"""Event bus — in-memory pub/sub for Server-Sent Events (SSE).

Lego block: no framework imports, pure asyncio, injectable.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextvars import ContextVar
from collections.abc import AsyncGenerator
from typing import Any, Protocol as TypingProtocol

logger = logging.getLogger(__name__)


class IEventBus(TypingProtocol):
    """Protocol for the EventBus — enables DI without coupling to the concrete class."""
    async def subscribe(self, client_id: str) -> asyncio.Queue: ...
    async def unsubscribe(self, client_id: str) -> None: ...
    async def publish(self, event_type: str, data: Any = None) -> None: ...
    async def stream(self, client_id: str, last_event_id: int | None = None) -> AsyncGenerator[str, None]: ...


class EventBus(IEventBus):
    """Simple in-memory pub/sub event bus with replay buffer.

    Usage::

        bus = EventBus()
        # Client subscribes
        async for event in bus.subscribe("client_123"):
            ...  # yields dicts like {"type": "new_message", "data": {...}}

        # Publisher
        await bus.publish("new_message", {"session_id": "...", "content": "..."})
    """

    MAX_REPLAY = 200  # keep last N events for reconnection replay

    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._ring: list[tuple[int, dict]] = []  # (seq, payload) ring buffer
        self._global_seq = 0

    async def subscribe(self, client_id: str) -> asyncio.Queue:
        """Register a client and return its event queue."""
        async with self._lock:
            if client_id not in self._queues:
                self._queues[client_id] = asyncio.Queue(maxsize=100)
                logger.info("SSE client connected: %s (total: %d)", client_id, len(self._queues))
            return self._queues[client_id]

    async def unsubscribe(self, client_id: str) -> None:
        """Remove a client."""
        async with self._lock:
            self._queues.pop(client_id, None)
            logger.info("SSE client disconnected: %s (total: %d)", client_id, len(self._queues))

    async def publish(self, event_type: str, data: Any = None) -> None:
        """Send an event to ALL connected clients and store in replay buffer."""
        payload = {"type": event_type, "data": data}
        async with self._lock:
            # Store in replay ring buffer
            self._global_seq += 1
            self._ring.append((self._global_seq, payload))
            if len(self._ring) > self.MAX_REPLAY:
                self._ring.pop(0)

            dead: list[str] = []
            for cid, q in self._queues.items():
                try:
                    q.put_nowait(payload)
                except asyncio.QueueFull:
                    dead.append(cid)
                    logger.warning("EventBus: client %s queue full, dropping", cid)
            for cid in dead:
                self._queues.pop(cid, None)

    async def stream(self, client_id: str, last_event_id: int | None = None) -> AsyncGenerator[str, None]:
        """Async generator that yields SSE-formatted strings with event IDs.

        If ``last_event_id`` is provided, replays buffered events since that ID
        before streaming live events.
        """
        import json as _json
        q = await self.subscribe(client_id)
        seq = 0

        # Replay buffered events if client reconnected
        if last_event_id is not None:
            async with self._lock:
                for ev_seq, payload in self._ring:
                    if ev_seq > last_event_id:
                        seq = ev_seq
                        yield f"id: {seq}\ndata: {_json.dumps(payload, default=str)}\n\n"
                seq = self._global_seq

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


_current_bus: ContextVar[IEventBus | None] = ContextVar("kairos_event_bus", default=None)


def set_event_bus(bus: IEventBus) -> None:
    """Set the EventBus instance for the current context."""
    _current_bus.set(bus)


def reset_event_bus() -> None:
    """Clear the current-context bus and restore lazy creation."""
    _current_bus.set(None)


def get_event_bus() -> IEventBus:
    """Get or create the EventBus for the current context."""
    bus = _current_bus.get()
    if bus is None:
        bus = EventBus()
        _current_bus.set(bus)
    return bus
