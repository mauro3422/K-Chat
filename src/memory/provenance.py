"""Resolve the local node id for data provenance tagging.

Lives in ``src/memory`` so storage modules don't need to import
``src.coordination`` directly. The coordinator is optional — when not
configured (e.g. running memory utilities outside the web app) this
helper returns an empty string, which the storage layer treats as
"origin unknown" via ``DEFAULT ''`` columns.
"""

from __future__ import annotations


def resolve_local_node_id() -> str:
    """Return the active ``NodeCoordinator.node_id`` or ``""`` when absent.

    Reads the ``ContextVar`` synchronously via ``peek_node_coordinator``.
    Safe to call from sync and async contexts — no side effects.
    """
    try:
        from src.coordination.node_state import peek_node_coordinator

        coordinator = peek_node_coordinator()
        if coordinator is None:
            return ""
        return getattr(coordinator, "node_id", "") or ""
    except Exception:
        return ""