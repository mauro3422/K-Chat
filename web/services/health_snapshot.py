from __future__ import annotations

import math
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio


def _text_or_default(value, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _float_or_default(value, default: float = 0.0) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
        return float(value)
    return default


def _bool_or_default(value, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _int_or_default(value, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _mapping_or_default(value, default: dict | None = None) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    return dict(default or {})


def _ping_sqlite_readonly(path: str) -> None:
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    conn = sqlite3.connect(f"file:{file_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
    try:
        conn.execute("SELECT 1")
    finally:
        conn.close()


def checks_are_healthy(checks: Mapping[str, str], *, testing: bool) -> bool:
    return all(
        value in {"ok", "configured", "not_configured"}
        or (testing and key == "database")
        or key in {"node_role", "cluster_name"}
        for key, value in checks.items()
    )


async def build_health_checks(cfg: Any, *, testing: bool) -> dict[str, str]:
    checks: dict[str, str] = {}

    try:
        db_path = _text_or_default(getattr(cfg, "sessions_db_path", None))
        if not db_path:
            raise FileNotFoundError("sessions_db_path not configured")

        await anyio.to_thread.run_sync(_ping_sqlite_readonly, db_path)
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "skipped" if testing else "error"

    try:
        api_key = getattr(cfg, "opencode_zen_api_key", None)
        checks["llm_provider"] = "configured" if api_key else "not_configured"
    except Exception:
        checks["llm_provider"] = "error"

    try:
        checks["node_role"] = _text_or_default(getattr(cfg, "node_role", None), "secondary")
        checks["cluster_name"] = _text_or_default(getattr(cfg, "cluster_name", None), "kairos")
    except Exception:
        checks["node_role"] = "error"
        checks["cluster_name"] = "error"

    return checks


def build_health_coordination(
    *,
    cfg: Any,
    coordinator_snapshot: Mapping[str, Any] | None,
    cluster: Mapping[str, Any] | None,
) -> dict[str, Any]:
    snapshot = _mapping_or_default(coordinator_snapshot)
    cluster_snapshot = _mapping_or_default(
        cluster,
        {
            "peer_count": 0,
            "reachable_peers": 0,
            "unreachable_peers": 0,
            "states": [],
            "errors": [],
        },
    )
    return {
        "node_id": _text_or_default(snapshot.get("node_id"), _text_or_default(getattr(cfg, "node_id", None), "")),
        "role": _text_or_default(snapshot.get("role"), _text_or_default(getattr(cfg, "node_role", None), "secondary")),
        "has_recent_primary": snapshot.get("has_recent_primary"),
        "peer_count": len(snapshot.get("peers", [])),
        "cluster": cluster_snapshot,
    }


def build_health_runtime(
    *,
    cfg: Any,
    coordinator_snapshot: Mapping[str, Any] | None,
    coordinator_role: str,
    queue_size: int,
    queue_pending: list[Any],
    lease_snapshot: Any,
    failover_snapshot: Mapping[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    coord_snapshot = _mapping_or_default(coordinator_snapshot)
    failover = _mapping_or_default(failover_snapshot)
    if lease_snapshot is not None:
        if hasattr(lease_snapshot, "to_dict"):
            lease_snapshot = lease_snapshot.to_dict()
        elif isinstance(lease_snapshot, Mapping):
            lease_snapshot = dict(lease_snapshot)
        else:
            lease_snapshot = None

    node_role = _text_or_default(getattr(cfg, "node_role", None), "secondary")
    sync = {
        "role": _text_or_default(coord_snapshot.get("role"), node_role),
        "is_primary": bool(coordinator_role == "primary"),
        "has_recent_primary": _bool_or_default(coord_snapshot.get("has_recent_primary", False), False),
        "memory_is_fresh": _bool_or_default(coord_snapshot.get("memory_is_fresh", True), True),
        "last_memory_revision": _float_or_default(coord_snapshot.get("last_memory_revision", 0.0), 0.0),
        "last_memory_sync": _float_or_default(coord_snapshot.get("last_memory_sync", 0.0), 0.0),
    }
    memory = {
        "queue_size": queue_size,
        "queue_pending": list(queue_pending or []),
        "lease": lease_snapshot,
        "freshness": {
            "last_revision": _float_or_default(coord_snapshot.get("last_memory_revision", 0.0), 0.0),
            "last_sync": _float_or_default(coord_snapshot.get("last_memory_sync", 0.0), 0.0),
            "is_fresh": _bool_or_default(coord_snapshot.get("memory_is_fresh", True), True),
        },
    }
    failover_payload = {
        "required_misses": _int_or_default(failover.get("required_misses", 2), 2),
        "miss_count": _int_or_default(failover.get("miss_count", 0), 0),
        "last_check_at": _float_or_default(failover.get("last_check_at", 0.0), 0.0),
        "last_primary_seen_at": _float_or_default(failover.get("last_primary_seen_at", 0.0), 0.0),
        "last_promotion_at": _float_or_default(failover.get("last_promotion_at", 0.0), 0.0),
        "last_action": _text_or_default(failover.get("last_action"), "idle"),
        "last_reason": _text_or_default(failover.get("last_reason"), ""),
        "promoted_role": _text_or_default(failover.get("promoted_role"), ""),
        "should_promote": _bool_or_default(failover.get("should_promote", False), False),
    }
    return sync, memory, failover_payload
