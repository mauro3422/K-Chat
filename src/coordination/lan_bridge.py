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
from src.coordination.embedding_job_queue import get_embedding_job_queue, replay_pending_embedding_jobs
from src.coordination.lan_auth import (
    LanRequestSignerProtocol,
    encode_json_body,
    is_sensitive_lan_request,
    request_path,
)
from src.coordination.lan_addressing import active_peer_urls, resolve_advertised_base_url
from src.coordination.lan_discovery import detect_lan_ip
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
        lan_ip_resolver: Callable[[], str] = detect_lan_ip,
        on_primary_yield: Callable[[str], None] | None = None,
        request_signer: LanRequestSignerProtocol | None = None,
    ) -> None:
        self._config = config
        self._coordinator = coordinator
        self._static_peer_urls = parse_peer_urls(getattr(config, "peer_urls", ""))
        self._discovered_peer_urls: dict[str, float] = {}
        self._client_factory = client_factory or (lambda: httpx.AsyncClient(timeout=3.0))
        self._lan_ip_resolver = lan_ip_resolver
        self._on_primary_yield = on_primary_yield
        self._request_signer = request_signer

    def _response_json(self, response: httpx.Response) -> dict:
        """Safely parse JSON response, returning {} for empty bodies."""
        try:
            return response.json() if response.content else {}
        except Exception:
            logger.warning("Failed to parse JSON response from %s", response.url)
            return {}

    @property
    def peer_urls(self) -> list[str]:
        return active_peer_urls(
            self._static_peer_urls,
            self._discovered_peer_urls,
            discovery_enabled=bool(getattr(self._config, "lan_discovery_enabled", True)),
        )

    def register_discovered_peer(self, peer_url: str, seen_at: float | None = None) -> None:
        normalized = peer_url.strip().rstrip("/")
        if normalized and normalized != self.base_url:
            self._discovered_peer_urls[normalized] = time.monotonic() if seen_at is None else seen_at

    def prune_discovered_peers(self, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        ttl = max(5.0, float(getattr(self._config, "lan_discovery_ttl", 20.0)))
        self._discovered_peer_urls = {
            peer: seen_at for peer, seen_at in self._discovered_peer_urls.items() if current - seen_at <= ttl
        }

    @property
    def base_url(self) -> str:
        return resolve_advertised_base_url(
            str(getattr(self._config, "node_base_url", "") or ""),
            str(getattr(self._config, "host", "") or ""),
            int(getattr(self._config, "port", 8000)),
            lan_ip_resolver=self._lan_ip_resolver,
        )

    @property
    def interval(self) -> float:
        ttl = float(getattr(self._config, "node_heartbeat_ttl", 15.0) or 15.0)
        return max(2.0, ttl / 2.0)

    async def broadcast_once(self) -> HeartbeatResult:
        self.prune_discovered_peers()
        result = HeartbeatResult(peers=self.peer_urls)
        peers = self.peer_urls
        if not peers:
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
            for peer in peers:
                try:
                    response = await self._request_with_retry(client, "post", f"{peer}/api/node/heartbeat", json=payload)
                    data = self._response_json(response)
                    peer_state = data.get("state", {}) if isinstance(data, dict) else {}
                    await self._coordinator.record_peer_heartbeat(
                        node_id=str(peer_state.get("node_id") or peer),
                        role=str(peer_state.get("role") or "secondary"),
                        base_url=peer,
                        metadata={"roundtrip_ms": response.elapsed.total_seconds() * 1000 if response.elapsed else 0.0},
                    )
                    await self._reconcile_primary(peer_state)
                    result.sent += 1
                    if peer_state.get("role") == "primary" and not await self._coordinator.is_primary():
                        try:
                            replayed = await self.replay_pending_memory_writes()
                            if replayed:
                                logger.info("Replayed %d queued memory writes via %s", len(replayed), peer)
                            embedding_replayed = await self.replay_pending_embedding_jobs()
                            if embedding_replayed:
                                logger.info("Replayed %d queued embedding jobs via %s", len(embedding_replayed), peer)
                        except Exception as exc:
                            result.failed += 1
                            result.errors.append({"peer": peer, "error": f"replay failed: {exc}"})
                except Exception as exc:
                    result.failed += 1
                    result.errors.append({"peer": peer, "error": str(exc)})
        return result

    async def _reconcile_primary(self, peer_state: dict[str, Any]) -> None:
        """Resolve a temporary dual-primary state deterministically."""
        if str(peer_state.get("role", "")).lower() != "primary" or not await self._coordinator.is_primary():
            return
        local_id = str(self._coordinator.node_id or "")
        peer_id = str(peer_state.get("node_id") or "")
        local_preferred = str(getattr(self._config, "node_role", "secondary")).lower() == "primary"
        peer_preferred = str(peer_state.get("preferred_role", "")).lower() == "primary"
        should_yield = (peer_preferred and not local_preferred) or (
            peer_preferred == local_preferred and bool(peer_id) and peer_id < local_id
        )
        if should_yield:
            await self._coordinator.demote()
            if self._on_primary_yield is not None:
                self._on_primary_yield("peer_primary_preferred")
            logger.warning("Dual primary reconciled: %s yielded to %s", local_id, peer_id)

    async def broadcast_event(self, event_type: str, data: Any = None) -> HeartbeatResult:
        result = HeartbeatResult(peers=self.peer_urls)
        peers = self.peer_urls
        if not peers:
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
            for peer in peers:
                try:
                    await self._request_with_retry(client, "post", f"{peer}/api/node/event", json=payload)
                    result.sent += 1
                except Exception as exc:
                    result.failed += 1
                    result.errors.append({"peer": peer, "error": str(exc)})
        return result

    async def request_memory_write(self, key: str, value: str, *, peer: str | None = None) -> dict[str, Any]:
        """Ask peers for permission to apply a memory write."""
        peers = self.peer_urls
        if not peers:
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
            peers = [peer] if peer else peers
            for peer in peers:
                try:
                    response = await self._request_with_retry(client, "post", f"{peer}/api/node/memory/request", json=payload)
                    data = self._response_json(response)
                    if isinstance(data, dict) and data.get("ok"):
                        return {"ok": True, "granted": bool(data.get("granted", True)), "queued": bool(data.get("queued", False)), "peer": peer, "response": data}
                except Exception as exc:
                    last_error = str(exc)
        return {"ok": False, "granted": False, "queued": False, "peer": None, "error": locals().get("last_error", "request failed")}

    async def request_embedding_jobs(
        self,
        items: list[dict[str, Any]],
        *,
        peer: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Ask a primary peer to process embedding work items."""
        peers = self.peer_urls
        if not peers:
            return {"ok": False, "queued": False, "peer": None, "error": "no peers configured"}

        payload = {
            "items": items,
            "dry_run": dry_run,
            "source": {
                "node_id": self._coordinator.node_id,
                "role": self._coordinator.role,
                "base_url": self.base_url,
            },
        }

        async with self._client_factory() as client:
            peers = [peer] if peer else peers
            for peer in peers:
                try:
                    response = await self._request_with_retry(client, "post", f"{peer}/api/node/embeddings/jobs", json=payload)
                    data = self._response_json(response)
                    if isinstance(data, dict) and data.get("ok"):
                        return {"ok": True, "queued": bool(data.get("queued", False)), "peer": peer, "response": data}
                except Exception as exc:
                    last_error = str(exc)
        return {"ok": False, "queued": False, "peer": None, "error": locals().get("last_error", "request failed")}

    async def request_memory_snapshot(self, *, key_pattern: str = "", peer: str | None = None) -> dict[str, Any]:
        """Ask a peer for a complete memory snapshot."""
        peers = self.peer_urls
        if not peers:
            return {"ok": False, "peer": None, "error": "no peers configured"}

        async with self._client_factory() as client:
            peers = [peer] if peer else peers
            for peer in peers:
                try:
                    response = await self._request_with_retry(client, "get", f"{peer}/api/memory/diagnostics", params={"key_pattern": key_pattern})
                    data = self._response_json(response)
                    if isinstance(data, dict) and data.get("ok"):
                        return {"ok": True, "peer": peer, "snapshot": data}
                except Exception as exc:
                    last_error = str(exc)
        return {"ok": False, "peer": None, "error": locals().get("last_error", "snapshot request failed")}

    async def request_peer_state(self, *, peer: str) -> dict[str, Any]:
        """Ask a specific peer for its local node state snapshot."""
        if peer not in self.peer_urls:
            return {"ok": False, "peer": peer, "error": "peer not configured"}

        async with self._client_factory() as client:
            try:
                response = await self._request_with_retry(client, "get", f"{peer}/api/node/state")
                data = self._response_json(response)
                if isinstance(data, dict):
                    return {"ok": True, "peer": peer, "state": data}
            except Exception as exc:
                return {"ok": False, "peer": peer, "error": str(exc)}
        return {"ok": False, "peer": peer, "error": "state request failed"}

    async def request_peer_diagnostics(self, *, peer: str, key_pattern: str = "") -> dict[str, Any]:
        """Ask a specific peer for its full diagnostics snapshot."""
        if peer not in self.peer_urls:
            return {"ok": False, "peer": peer, "error": "peer not configured"}

        async with self._client_factory() as client:
            try:
                response = await self._request_with_retry(client, "get", f"{peer}/api/node/diagnostics", params={"key_pattern": key_pattern})
                data = self._response_json(response)
                if isinstance(data, dict):
                    return {"ok": True, "peer": peer, "snapshot": data}
            except Exception as exc:
                return {"ok": False, "peer": peer, "error": str(exc)}
        return {"ok": False, "peer": peer, "error": "diagnostics request failed"}

    async def request_peer_memory_snapshots(self, *, key_pattern: str = "") -> dict[str, Any]:
        """Ask every peer for its memory diagnostics snapshot."""
        peers = self.peer_urls
        if not peers:
            return {"ok": False, "peers": [], "snapshots": [], "errors": []}

        result: dict[str, Any] = {"ok": True, "peers": self.peer_urls, "snapshots": [], "errors": []}
        async with self._client_factory() as client:
            responses = await self._request_all_peers(
                client,
                peers,
                "/api/memory/diagnostics",
                params={"key_pattern": key_pattern},
            )
        for peer, data, error in responses:
            if error is not None:
                result["errors"].append({"peer": peer, "error": error})
            elif data is None:
                result["errors"].append({"peer": peer, "error": "invalid response"})
            else:
                enriched = dict(data)
                enriched.setdefault("peer_url", peer)
                result["snapshots"].append(enriched)
        return result

    async def request_session_directory(self, *, limit: int = 50) -> dict[str, Any]:
        """Ask peers for their session directory snapshots."""
        peers = self.peer_urls
        if not peers:
            return {"ok": False, "peers": [], "sessions": [], "errors": []}

        result: dict[str, Any] = {"ok": True, "peers": self.peer_urls, "sessions": [], "errors": []}
        async with self._client_factory() as client:
            for peer in peers:
                try:
                    response = await self._request_with_retry(client, "get", f"{peer}/api/node/sessions", params={"limit": limit})
                    data = self._response_json(response)
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
                        # The peer endpoint describes its own rows as local. From
                        # this node they are always remote, so these fields must
                        # override the peer payload instead of using setdefault().
                        enriched["source_mode"] = "peer"
                        enriched["source_url"] = peer
                        node_id = str(node.get("node_id") or session.get("node_id") or peer).strip() or peer
                        enriched.setdefault("node_id", node_id)
                        enriched.setdefault("node_role", str(node.get("role") or session.get("node_role") or "secondary").strip() or "secondary")
                        enriched["node_platform"] = str(node.get("node_platform") or session.get("node_platform") or "").strip().lower()
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
        peers = self.peer_urls
        if not peers:
            return {"ok": False, "peers": [], "states": [], "errors": []}

        result: dict[str, Any] = {"ok": True, "peers": self.peer_urls, "states": [], "errors": []}
        async with self._client_factory() as client:
            responses = await self._request_all_peers(client, peers, "/api/node/state")
        for peer, data, error in responses:
            if error is not None:
                result["errors"].append({"peer": peer, "error": error})
            elif data is None:
                result["errors"].append({"peer": peer, "error": "invalid response"})
            else:
                enriched = dict(data)
                enriched.setdefault("source_url", peer)
                enriched.setdefault("peer_url", peer)
                result["states"].append(enriched)
        return result

    async def _request_all_peers(
        self,
        client: Any,
        peers: list[str],
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> list[tuple[str, dict[str, Any] | None, str | None]]:
        """Request one endpoint from every peer concurrently, preserving peer order."""
        concurrency = max(1, int(getattr(self._config, "lan_snapshot_max_concurrency", 4)))
        semaphore = asyncio.Semaphore(concurrency)

        async def _request_peer(peer: str) -> tuple[str, dict[str, Any] | None, str | None]:
            try:
                async with semaphore:
                    response = await self._request_with_retry(client, "get", f"{peer}{path}", params=params)
                data = self._response_json(response)
                return peer, data if isinstance(data, dict) else None, None
            except Exception as exc:
                return peer, None, str(exc)

        return await asyncio.gather(*(_request_peer(peer) for peer in peers))

    async def replay_pending_memory_writes(self) -> list[dict[str, str]]:
        """Replay queued writes against the first reachable primary peer."""
        queue = get_memory_write_queue(self._config)
        if not queue:
            return []

        primary_peer = None
        for peer in self.peer_urls:
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

    async def replay_pending_embedding_jobs(self) -> list[dict[str, Any]]:
        """Replay queued embedding jobs against the first reachable primary peer."""
        queue = get_embedding_job_queue(self._config)
        if not queue:
            return []

        primary_peer = None
        for peer in self.peer_urls:
            for heartbeat in self._coordinator.snapshot().get("peers", []):
                if heartbeat.get("base_url") == peer and heartbeat.get("role") == "primary":
                    primary_peer = peer
                    break
            if primary_peer:
                break

        if primary_peer is None:
            return []

        async def _deliver(item):
            return await self.request_embedding_jobs([item.to_dict()], peer=primary_peer)

        return await replay_pending_embedding_jobs(queue, _deliver)

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
                request_kwargs = dict(kwargs)
                body = b""
                if "json" in request_kwargs:
                    body = encode_json_body(request_kwargs["json"])
                elif isinstance(request_kwargs.get("content"), bytes):
                    body = request_kwargs["content"]

                if self._request_signer is None:
                    if is_sensitive_lan_request(method, url):
                        raise RuntimeError(
                            "LAN request signing is not configured for a sensitive operation"
                        )
                else:
                    headers = dict(request_kwargs.get("headers", {}))
                    headers.update(
                        self._request_signer.sign_headers(
                            method,
                            request_path(url),
                            body,
                        )
                    )
                    request_kwargs["headers"] = headers

                response = await getattr(client, method)(url, **request_kwargs)
                response.raise_for_status()
                return response
            except Exception as exc:
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                await anyio.sleep(base_delay * (attempt + 1))
        assert last_exc is not None
        raise last_exc
