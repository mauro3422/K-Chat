"""WebSocket client — connects from the bot to the web server's WS endpoint
to stream live tokens (reasoning, content, tool calls) to the web UI.

Singleton pattern: the bot creates one connection at startup and reuses it.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

logger = logging.getLogger(__name__)


def _get_ws_url() -> str:
    """Get the WebSocket URL, configurable via env KAIROS_WEB_URL."""
    base = os.environ.get("KAIROS_WEB_URL", "http://127.0.0.1:8000")
    # Normalize both HTTP(S) and WS(S) inputs to a websocket URL.
    if base.startswith("wss://") or base.startswith("https://"):
        ws_base = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
    elif base.startswith("ws://") or base.startswith("http://"):
        ws_base = base.replace("http://", "ws://", 1)
    else:
        ws_base = "ws://" + base.lstrip("/")
    return ws_base.rstrip("/") + "/api/ws/events"


class BotWSClient:
    """Persistent WebSocket connection from the bot to the web server.

    Usage::

        client = BotWSClient()
        await client.connect()          # at startup
        await client.send_event(...)    # during streaming
        await client.disconnect()       # at shutdown
    """

    def __init__(self) -> None:
        self._ws = None
        self._ws_lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None
        self._connected = asyncio.Event()

    async def connect(self) -> None:
        """Connect to the web server WebSocket endpoint."""
        url = _get_ws_url()
        try:
            import websockets
            self._ws = await websockets.connect(url, ping_interval=30, ping_timeout=10)
            logger.info("WS client connected to %s", url)
            self._connected.set()
            # Start background listener (detects disconnection)
            self._reconnect_task = asyncio.create_task(self._keep_alive())
        except Exception as e:
            logger.warning("WS client connection failed (non-fatal): %s — SSE notify falls back to HTTP", e)
            self._connected.set()  # Don't block — fall back to HTTP notify

    async def send_event(self, event_type: str, data: dict) -> None:
        """Send an event through the WebSocket connection.

        Thread-safe via asyncio.Lock — multiple concurrent sessions can
        call send_event simultaneously without corrupting the WS stream.
        Falls back to HTTP POST if WS is down.
        """
        async with self._ws_lock:
            if self._ws:
                try:
                    payload = json.dumps({"type": event_type, "data": data})
                    await self._ws.send(payload)
                    return
                except Exception:
                    logger.warning("WS send failed, reconnecting: %s", event_type)
                    self._ws = None
                    # Try to reconnect once
                    try:
                        await self.connect()
                    except Exception:
                        pass

        # Fallback: HTTP notify to ALL configured URLs
        try:
            from channels.telegram.adapter import _notify_all
            await _notify_all(event_type, data)
        except Exception:
            logger.warning("HTTP notify fallback failed: %s", event_type)

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        logger.info("WS client disconnected")

    async def _keep_alive(self) -> None:
        """Monitor connection health and reconnect if needed."""
        import websockets
        try:
            async for _ in self._ws:
                # Consume any incoming messages (mostly pongs)
                pass
        except websockets.ConnectionClosed:
            logger.info("WS connection closed, will reconnect on next event")
            self._ws = None


