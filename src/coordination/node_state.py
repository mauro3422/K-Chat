"""Node coordination state for LAN bridge and leader tracking."""

from __future__ import annotations

import asyncio
import platform
import socket
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from src.config_loader import Config


def _default_node_id() -> str:
    host = socket.gethostname().strip()
    return host or "kairos-node"


def _parse_peer_urls(raw: str | None) -> list[str]:
    if not raw:
        return []
    peers: list[str] = []
    for chunk in raw.replace("\n", ",").split(","):
        peer = chunk.strip().rstrip("/")
        if peer:
            peers.append(peer)
    return peers


@dataclass(slots=True)
class PeerHeartbeat:
    node_id: str
    role: str
    base_url: str = ""
    last_seen: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "role": self.role,
            "base_url": self.base_url,
            "last_seen": self.last_seen,
            "metadata": dict(self.metadata),
        }


class NodeCoordinator:
    """Tracks local node identity, role, and remote heartbeats."""

    def __init__(self, config: Config | None = None) -> None:
        self._config = config
        self._lock = asyncio.Lock()
        self._node_id = (config.node_id if config and getattr(config, "node_id", "") else _default_node_id())
        self._role = (config.node_role if config and getattr(config, "node_role", "") else "secondary")
        configured_platform = str(getattr(config, "node_platform", "") if config else "").strip().lower()
        self._platform = configured_platform or platform.system().strip().lower() or "unknown"
        self._cluster_name = (config.cluster_name if config and getattr(config, "cluster_name", "") else "default")
        self._heartbeat_ttl = float(getattr(config, "node_heartbeat_ttl", 15.0) if config else 15.0)
        self._peer_urls = _parse_peer_urls(getattr(config, "peer_urls", "") if config else "")
        self._last_heartbeat = time.time()
        self._last_primary_seen = 0.0
        self._last_memory_revision = 0.0
        self._last_memory_sync = 0.0
        self._peers: dict[str, PeerHeartbeat] = {}

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def role(self) -> str:
        return self._role

    @property
    def cluster_name(self) -> str:
        return self._cluster_name

    @property
    def heartbeat_ttl(self) -> float:
        return self._heartbeat_ttl

    @property
    def peer_urls(self) -> list[str]:
        return list(self._peer_urls)

    @property
    def config(self) -> Config | None:
        return self._config

    async def beat(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            self._last_heartbeat = time.time()
            if self._role == "primary":
                self._last_primary_seen = self._last_heartbeat
            return self.snapshot(metadata=metadata)

    async def set_role(self, role: str) -> None:
        async with self._lock:
            self._role = role if role in {"primary", "secondary"} else "secondary"

    async def set_node_id(self, node_id: str) -> None:
        async with self._lock:
            clean = node_id.strip()
            if clean:
                self._node_id = clean

    async def record_peer_heartbeat(
        self,
        node_id: str,
        role: str,
        base_url: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        peer = PeerHeartbeat(
            node_id=node_id.strip() or "peer",
            role=role if role in {"primary", "secondary"} else "secondary",
            base_url=base_url.strip(),
            last_seen=time.time(),
            metadata=dict(metadata or {}),
        )
        async with self._lock:
            self._peers[peer.node_id] = peer
            if peer.role == "primary":
                self._last_primary_seen = peer.last_seen
            return self.snapshot()

    async def promote(self) -> dict[str, Any]:
        async with self._lock:
            self._role = "primary"
            self._last_primary_seen = time.time()
            self._last_heartbeat = self._last_primary_seen
            return self.snapshot()

    async def demote(self) -> dict[str, Any]:
        async with self._lock:
            self._role = "secondary"
            self._last_heartbeat = time.time()
            return self.snapshot()

    async def is_primary(self) -> bool:
        async with self._lock:
            return self._role == "primary"

    async def has_recent_primary(self) -> bool:
        async with self._lock:
            if self._last_primary_seen <= 0:
                return False
            return (time.time() - self._last_primary_seen) <= self._heartbeat_ttl

    async def mark_memory_revision(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            self._last_memory_revision = time.time()
            return self.snapshot(metadata=metadata)

    async def mark_memory_sync(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        async with self._lock:
            self._last_memory_sync = time.time()
            return self.snapshot(metadata=metadata)

    def snapshot(self, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        peers = []
        for peer in self._peers.values():
            peers.append(peer.to_dict())
        return {
            "node_id": self._node_id,
            "role": self._role,
            "node_platform": self._platform,
            "cluster_name": self._cluster_name,
            "heartbeat_ttl": self._heartbeat_ttl,
            "last_heartbeat": self._last_heartbeat,
            "last_memory_revision": self._last_memory_revision,
            "last_memory_sync": self._last_memory_sync,
            "healthy": (now - self._last_heartbeat) <= self._heartbeat_ttl,
            "has_recent_primary": (now - self._last_primary_seen) <= self._heartbeat_ttl if self._last_primary_seen else False,
            "memory_is_fresh": self._last_memory_revision <= 0 or self._last_memory_revision >= self._last_memory_sync,
            "peers": sorted(peers, key=lambda item: item["node_id"]),
            "metadata": dict(metadata or {}),
        }


_current_coordinator: ContextVar[NodeCoordinator | None] = ContextVar("kairos_node_coordinator", default=None)


def configure_node_coordinator(coordinator: NodeCoordinator | None) -> None:
    _current_coordinator.set(coordinator)


def reset_node_coordinator() -> None:
    _current_coordinator.set(None)


def peek_node_coordinator() -> NodeCoordinator | None:
    return _current_coordinator.get()


def get_node_coordinator(config: Config | None = None) -> NodeCoordinator:
    coordinator = _current_coordinator.get()
    if coordinator is not None:
        return coordinator
    coordinator = NodeCoordinator(config=config)
    _current_coordinator.set(coordinator)
    return coordinator
