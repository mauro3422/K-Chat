"""LAN heartbeat bridge for node-to-node coordination."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

import anyio
import httpx

from src.config_loader import Config
from src.coordination.memory_write_queue import get_memory_write_queue, replay_pending_memory_writes
from src.coordination.node_state import NodeCoordinator

logger = logging.getLogger(__name__)


def parse_peer_urls(raw: str | None) -> list[str]:
    if not raw:
        return []
    peers: list[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        peer = chunk.strip().rstrip("/")
        if peer:
            peers.append(peer)
    return peers


@dataclass(slots=True)
class HeartbeatResult:
    sent: int = 0
    failed: int = 0
    peers: list[str] = field(default_factory=list)
    errors: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sent": self.sent,
            "failed": self.failed,
            "peers": list(self.peers),
            "errors": [dict(item) for item in self.errors],
        }


class NodeLanBridge:
    """Broadcasts local node heartbeats to configured LAN peers."""

    def __init__(
        self,
        config: Config,
        coordinator: NodeCoordinator,
        *,
        client_factory: Callable[[], httpx.AsyncClient] | None = None,
    ) -> None:
        self._config = config
        self._coordinator = coordinator
        self._peer_urls = parse_peer_urls(getattr(config, "peer_urls", ""))
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=3.0))

    @property
    def peer_urls(self) -> list[str]:
        return list(self._peer_urls)

    @property
    def base_url(self) -> str:
        host = (self._config.host or "127.0.0.1").strip() or "127.0.0.1"
        return f"http://{host}:{self._config.port}"

    @property
    def interval(self) -> float:
        ttl = float(getattr(self._config, "node_heartbeat_ttl", 15.0) or 15.0)
        return max(2.0, ttl / 2.0)

    async def broadcast_once(self) -> HeartbeatResult:
        result = HeartbeatResult(peers=self.peer_urls)
        if not self._peer_urls:
            await self._coordinator.beat(metadata={"lan_bridge": "disabled"})
            return result

        local_state = await self._coordinator.beat(metadata={"lan_bridge": "heartbeat"})
        payload = {
            "node_id": local_state["node_id"],
            "role": local_state["role"],
            "base_url": self.base_url,
            "metadata": {
                "cluster_name": local_state.get("cluster_name"),
                "heartbeat_ttl": local_state.get("heartbeat_ttl"),
                "timestamp": time.time(),
            },
        }

        async with self._client_factory() as client:
            for peer in self._peer_urls:
                try:
                    response = await self._request_with_retry(client, "post", f"{peer}/api/node/heartbeat", json=payload)
                    data = response.json() if response.content else {}
                    peer_state = data.get("state", {}) if isinstance(data, dict) else {}
                    await self._coordinator.record_peer_heartbeat(
                        node_id=str(peer_state.get("node_id") or peer),
                        role=str(peer_state.get("role") or "secondary"),
                        base_url=peer,
                        metadata={"roundtrip_ms": response.elapsed.total_seconds() * 1000 if response.elapsed else 0.0},
                    )
                    result.sent += 1
                    if peer_state.get("role") == "primary" and not await self._coordinator.is_primary():
                        try:
                            replayed = await self.replay_pending_memory_writes()
                            if replayed:
                                logger.info("Replayed %d queued memory writes via %s", len(replayed), peer)
                        except Exception as exc:
                            result.failed += 1
                            result.errors.append({"peer": peer, "error": f"replay failed: {exc}"})
                except Exception as exc:
                    result.failed += 1
                    result.errors.append({"peer": peer, "error": str(exc)})
        return result

    async def broadcast_event(self, event_type: str, data: Any = None) -> HeartbeatResult:
        result = HeartbeatResult(peers=self.peer_urls)
        if not self._peer_urls:
            return result

        payload = {
            "type": event_type,
            "data": data,
            "source": {
                "node_id": self._coordinator.node_id,
                "role": self._coordinator.role,
                "base_url": self.base_url,
            },
        }

        async with self._client_factory() as client:
            for peer in self._peer_urls:
                try:
                    await self._request_with_retry(client, "post", f"{peer}/api/node/event", json=payload)
                    result.sent += 1
                except Exception as exc:
                    result.failed += 1
                    result.errors.append({"peer": peer, "error": str(exc)})
        return result

    async def request_memory_write(self, key: str, value: str, *, peer: str | None = None) -> dict[str, Any]:
        """Ask peers for permission to apply a memory write."""
        if not self._peer_urls:
            return {"ok": False, "granted": False, "queued": False, "peer": None, "error": "no peers configured"}

        payload = {
            "key": key,
            "value": value,
            "source": {
                "node_id": self._coordinator.node_id,
                "role": self._coordinator.role,
                "base_url": self.base_url,
            },
        }

        async with self._client_factory() as client:
            peers = [peer] if peer else self._peer_urls
            for peer in peers:
                try:
                    response = await self._request_with_retry(client, "post", f"{peer}/api/node/memory/request", json=payload)
                    data = response.json() if response.content else {}
                    if isinstance(data, dict) and data.get("ok"):
                        return {"ok": True, "granted": bool(data.get("granted", True)), "queued": bool(data.get("queued", False)), "peer": peer, "response": data}
                except Exception as exc:
                    last_error = str(exc)
        return {"ok": False, "granted": False, "queued": False, "peer": None, "error": locals().get("last_error", "request failed")}

    async def request_memory_snapshot(self, *, key_pattern: str = "") -> dict[str, Any]:
        """Ask a peer for a complete memory snapshot."""
        if not self._peer_urls:
            return {"ok": False, "peer": None, "error": "no peers configured"}

        async with self._client_factory() as client:
            for peer in self._peer_urls:
                try:
                    response = await self._request_with_retry(client, "get", f"{peer}/api/memory/diagnostics", params={"key_pattern": key_pattern})
                    data = response.json() if response.content else {}
                    if isinstance(data, dict) and data.get("ok"):
                        return {"ok": True, "peer": peer, "snapshot": data}
                except Exception as exc:
                    last_error = str(exc)
        return {"ok": False, "peer": None, "error": locals().get("last_error", "snapshot request failed")}

    async def request_peer_memory_snapshots(self, *, key_pattern: str = "") -> dict[str, Any]:
        """Ask every peer for its memory diagnostics snapshot."""
        if not self._peer_urls:
            return {"ok": False, "peers": [], "snapshots": [], "errors": []}

        result: dict[str, Any] = {"ok": True, "peers": self.peer_urls, "snapshots": [], "errors": []}
        async with self._client_factory() as client:
            for peer in self._peer_urls:
                try:
                    response = await self._request_with_retry(client, "get", f"{peer}/api/memory/diagnostics", params={"key_pattern": key_pattern})
                    data = response.json() if response.content else {}
                    if not isinstance(data, dict):
                        result["errors"].append({"peer": peer, "error": "invalid response"})
                        continue
                    enriched = dict(data)
                    enriched.setdefault("peer_url", peer)
                    result["snapshots"].append(enriched)
                except Exception as exc:
                    result["errors"].append({"peer": peer, "error": str(exc)})
        return result

    async def request_session_directory(self, *, limit: int = 50) -> dict[str, Any]:
        """Ask peers for their session directory snapshots."""
        if not self._peer_urls:
            return {"ok": False, "peers": [], "sessions": [], "errors": []}

        result: dict[str, Any] = {"ok": True, "peers": self.peer_urls, "sessions": [], "errors": []}
        async with self._client_factory() as client:
            for peer in self._peer_urls:
                try:
                    response = await self._request_with_retry(client, "get", f"{peer}/api/node/sessions", params={"limit": limit})
                    data = response.json() if response.content else {}
                    if not isinstance(data, dict):
                        result["errors"].append({"peer": peer, "error": "invalid response"})
                        continue
                    sessions = data.get("sessions", [])
                    if not isinstance(sessions, list):
                        result["errors"].append({"peer": peer, "error": "invalid sessions payload"})
                        continue
                    node = data.get("node", {})
                    if not isinstance(node, dict):
                        node = {}
                    for session in sessions:
                        if not isinstance(session, dict):
                            continue
                        enriched = dict(session)
                        enriched.setdefault("source_mode", "peer")
                        enriched.setdefault("source_url", peer)
                        enriched.setdefault("node_id", str(node.get("node_id") or session.get("node_id") or peer).strip() or peer)
                        enriched.setdefault("node_role", str(node.get("role") or session.get("node_role") or "secondary").strip() or "secondary")
                        enriched.setdefault("cluster_name", str(node.get("cluster_name") or session.get("cluster_name") or "kairos").strip() or "kairos")
                        result["sessions"].append(enriched)
                except Exception as exc:
                    result["errors"].append({"peer": peer, "error": str(exc)})
        return result

    async def request_peer_states(self) -> dict[str, Any]:
        """Ask peers for their local node state snapshots.

        This intentionally targets /api/node/state instead of /api/node/sync/status
        so we can aggregate peer health without recursive peer fan-out.
        """
        if not self._peer_urls:
            return {"ok": False, "peers": [], "states": [], "errors": []}

        result: dict[str, Any] = {"ok": True, "peers": self.peer_urls, "states": [], "errors": []}
        async with self._client_factory() as client:
            for peer in self._peer_urls:
                try:
                    response = await self._request_with_retry(client, "get", f"{peer}/api/node/state")
                    data = response.json() if response.content else {}
                    if not isinstance(data, dict):
                        result["errors"].append({"peer": peer, "error": "invalid response"})
                        continue
                    enriched = dict(data)
                    enriched.setdefault("source_url", peer)
                    enriched.setdefault("peer_url", peer)
                    result["states"].append(enriched)
                except Exception as exc:
                    result["errors"].append({"peer": peer, "error": str(exc)})
        return result

    async def replay_pending_memory_writes(self) -> list[dict[str, str]]:
        """Replay queued writes against the first reachable primary peer."""
        queue = get_memory_write_queue(self._config)
        if not queue:
            return []

        primary_peer = None
        for peer in self._peer_urls:
            for heartbeat in self._coordinator.snapshot().get("peers", []):
                if heartbeat.get("base_url") == peer and heartbeat.get("role") == "primary":
                    primary_peer = peer
                    break
            if primary_peer:
                break

        if primary_peer is None:
            return []

        async def _deliver(item):
            return await self.request_memory_write(item.key, item.value, peer=primary_peer)

        return await replay_pending_memory_writes(queue, _deliver)

    async def _request_with_retry(
        self,
        client: Any,
        method: str,
        url: str,
        *,
        attempts: int = 3,
        base_delay: float = 0.1,
        **kwargs: Any,
    ) -> Any:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                response = await getattr(client, method)(url, **kwargs)
                response.raise_for_status()
                return response
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                await anyio.sleep(base_delay * (attempt + 1))
        assert last_exc is not None
        raise last_exc

    async def run_loop(self, stop_event: asyncio.Event | None = None) -> None:
        stop = stop_event or asyncio.Event()
        while not stop.is_set():
            await self.broadcast_once()
            try:
                await asyncio.wait_for(stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue
