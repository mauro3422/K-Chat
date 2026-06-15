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
    # Replace http/https with ws/wss
    if base.startswith("https"):
        ws_base = base.replace("https", "wss", 1)
    else:
        ws_base = base.replace("http", "ws", 1)
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

        If the connection is down, falls back to HTTP POST /api/events/notify.
        """
        if self._ws:
            try:
                payload = json.dumps({"type": event_type, "data": data})
                await self._ws.send(payload)
                return
            except Exception:
                logger.warning("WS send failed, falling back to HTTP: %s", event_type)
                self._ws = None

        # Fallback: HTTP notify (same as new_message path)
        try:
            import httpx
            url = _get_ws_url().replace("/api/ws/events", "/api/events/notify")
            async with httpx.AsyncClient() as client:
                await client.post(url, json={"type": event_type, "data": data}, timeout=3)
        except Exception:
            logger.warning("HTTP notify fallback also failed: %s", event_type)

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


# Module-level singleton
_client: BotWSClient | None = None


def get_ws_client() -> BotWSClient:
    """Get or create the global BotWSClient singleton."""
    global _client
    if _client is None:
        _client = BotWSClient()
    return _client
