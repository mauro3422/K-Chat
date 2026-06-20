"""Leadership lease used to avoid split-brain during failover."""

from __future__ import annotations

from contextvars import ContextVar

from src.config_loader import Config
from src.memory.memory_db_path import resolve_memory_db_path

from .memory_lease import MemoryLeaseManager


def _default_leader_lease_path(config: Config | None = None) -> str:
    return f"{resolve_memory_db_path(config)}.leader.json"


_current_leader_lease_manager: ContextVar[MemoryLeaseManager | None] = ContextVar(
    "kairos_leader_lease_manager",
    default=None,
)


def configure_leader_lease_manager(manager: MemoryLeaseManager | None) -> None:
    _current_leader_lease_manager.set(manager)


def reset_leader_lease_manager() -> None:
    _current_leader_lease_manager.set(None)


def get_leader_lease_manager(config: Config | None = None) -> MemoryLeaseManager:
    manager = _current_leader_lease_manager.get()
    if manager is None:
        manager = MemoryLeaseManager(config=config, lease_path=_default_leader_lease_path(config))
        _current_leader_lease_manager.set(manager)
    return manager

