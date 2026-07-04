"""Lightweight lease file used to guard curated memory writes."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.config_loader import Config
from src.memory.memory_db_path import resolve_memory_db_path

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class MemoryLease:
    owner_node_id: str
    acquired_at: float
    updated_at: float
    expires_at: float
    reason: str = "memory_write"

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_node_id": self.owner_node_id,
            "acquired_at": self.acquired_at,
            "updated_at": self.updated_at,
            "expires_at": self.expires_at,
            "reason": self.reason,
        }


class MemoryLeaseManager:
    """Process-local helper that persists a soft lease next to memory.db."""

    def __init__(self, config: Config | None = None, lease_path: str | None = None) -> None:
        self._config = config
        self._lease_path = Path(lease_path or f"{resolve_memory_db_path(config)}.lease.json")
        self._lock = threading.Lock()
        self._default_ttl = float(getattr(config, "node_heartbeat_ttl", 15.0) if config else 15.0)

    @property
    def lease_path(self) -> str:
        return str(self._lease_path)

    def snapshot(self) -> MemoryLease | None:
        with self._lock:
            return self._read_lease()

    def acquire(self, owner_node_id: str, *, ttl: float | None = None, reason: str = "memory_write") -> MemoryLease | None:
        owner = owner_node_id.strip()
        if not owner:
            return None
        lease_ttl = float(ttl or self._default_ttl)
        now = time.time()
        with self._lock:
            current = self._read_lease()
            if current and current.owner_node_id != owner and current.expires_at > now:
                return None

            lease = MemoryLease(
                owner_node_id=owner,
                acquired_at=current.acquired_at if current and current.owner_node_id == owner else now,
                updated_at=now,
                expires_at=now + lease_ttl,
                reason=reason,
            )
            self._write_lease(lease)
            return lease

    def release(self, owner_node_id: str) -> bool:
        owner = owner_node_id.strip()
        if not owner:
            return False
        with self._lock:
            current = self._read_lease()
            if current is None:
                return True
            if current.owner_node_id != owner:
                return False
            try:
                self._lease_path.unlink(missing_ok=True)
            except Exception:
                logger.warning("Failed to unlink lease file: %s", self._lease_path)
                return False
            return True

    def is_active(self, owner_node_id: str | None = None) -> bool:
        lease = self.snapshot()
        if lease is None:
            return False
        if owner_node_id is not None and lease.owner_node_id != owner_node_id.strip():
            return False
        return lease.expires_at > time.time()

    def _read_lease(self) -> MemoryLease | None:
        if not self._lease_path.exists():
            return None
        try:
            raw = json.loads(self._lease_path.read_text(encoding="utf-8"))
            lease = MemoryLease(
                owner_node_id=str(raw.get("owner_node_id", "")).strip(),
                acquired_at=float(raw.get("acquired_at", 0.0)),
                updated_at=float(raw.get("updated_at", 0.0)),
                expires_at=float(raw.get("expires_at", 0.0)),
                reason=str(raw.get("reason", "memory_write")),
            )
        except Exception:
            logger.exception("Failed to parse lease file: %s", self._lease_path)
            return None
        if not lease.owner_node_id:
            return None
        if lease.expires_at <= time.time():
            return lease
        return lease

    def _write_lease(self, lease: MemoryLease) -> None:
        self._lease_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._lease_path.with_suffix(self._lease_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(lease.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.replace(tmp_path, self._lease_path)
        except OSError as e:
            logger.error("Failed to persist lease file (disk full?): %s", e)


_current_lease_manager: ContextVar[MemoryLeaseManager | None] = ContextVar("kairos_memory_lease_manager", default=None)


def configure_memory_lease_manager(manager: MemoryLeaseManager | None) -> None:
    _current_lease_manager.set(manager)


def reset_memory_lease_manager() -> None:
    _current_lease_manager.set(None)


def get_memory_lease_manager(config: Config | None = None) -> MemoryLeaseManager:
    manager = _current_lease_manager.get()
    if manager is None:
        manager = MemoryLeaseManager(config=config)
        _current_lease_manager.set(manager)
    return manager

