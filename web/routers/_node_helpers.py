"""Shared provider helpers for node routers.

These ``_get_*`` functions resolve runtime dependencies (coordinator, bridge,
queue, lease manager, etc.) from the FastAPI ``request.app.state`` — the
composition root stores everything there. They live here (not in each router)
to avoid duplication. The ``_`` prefix on the module name follows the existing
convention in ``web/routers/`` (``_memory_snapshot.py``, ``_request_repos.py``)
signaling "shared private helper module" — auto-discovery in ``app_factory.py``
skips files starting with ``_``.
"""

from __future__ import annotations

from fastapi import Request

from src.api.repos import get_repos
from src.coordination.lan_bridge import NodeLanBridge
from src.coordination.leader_lease import get_leader_lease_manager
from src.coordination.memory_write_queue import get_memory_write_queue
from src.coordination.node_state import NodeCoordinator, get_node_coordinator
from web.routers._request_repos import request_repos
from web.services.peer_cluster_snapshot import build_peer_cluster_snapshot
from web.services.event_bus import IEventBus, get_event_bus
from web.services.failover_state import get_failover_state


def _get_coordinator(request: Request) -> NodeCoordinator:
    return getattr(request.app.state, "node_coordinator", None) or get_node_coordinator(
        getattr(request.app.state, "config", None)
    )


def _request_repos(request: Request | None):
    """Wrapper for ``_request_repos.request_repos`` that injects the default
    ``get_repos`` fallback. Accepts ``None`` so callers that may run outside an
    HTTP context (e.g. federated fetch helpers) can use it without breaking.
    """
    return request_repos(request, fallback=get_repos)


def _get_event_bus(request: Request) -> IEventBus:
    return getattr(request.app.state, "event_bus", None) or get_event_bus()


def _get_memory_queue(request: Request):
    return getattr(request.app.state, "memory_write_queue", None) or get_memory_write_queue()


def _get_save_memory_run(request: Request):
    runner = getattr(request.app.state, "save_memory_run", None)
    if runner is None:
        raise RuntimeError("save_memory runner not configured")
    return runner


def _get_node_bridge(request: Request) -> NodeLanBridge:
    bridge = getattr(request.app.state, "node_bridge", None)
    if bridge is None:
        coordinator = _get_coordinator(request)
        config = getattr(request.app.state, "config", None)
        bridge = NodeLanBridge(
            config=config,
            coordinator=coordinator,
            request_signer=getattr(request.app.state, "lan_request_signer", None),
        )
        request.app.state.node_bridge = bridge
    return bridge


def _get_leader_lease_manager(request: Request):
    return getattr(request.app.state, "leader_lease_manager", None) or get_leader_lease_manager(
        getattr(request.app.state, "config", None)
    )


def _get_failover_state(request: Request):
    return getattr(request.app.state, "failover_state", None) or get_failover_state()


def _request_base_url(request: Request | None) -> str:
    if request is None:
        return ""
    try:
        return str(request.base_url).rstrip("/")
    except Exception:
        return ""


async def _peer_cluster_state(request: Request) -> dict:
    bridge = _get_node_bridge(request)
    return await build_peer_cluster_snapshot(bridge)
