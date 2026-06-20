import sqlite3

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.config_loader import load_config

router = APIRouter()


def _text_or_default(value, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _float_or_default(value, default: float = 0.0) -> float:
    return value if isinstance(value, (int, float)) else default


def _bool_or_default(value, default: bool = False) -> bool:
    return value if isinstance(value, bool) else default


def _int_or_default(value, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else default


@router.get("/health")
async def health(request: Request):
    checks = {}
    cfg = getattr(request.app.state, "config", None) or load_config()
    testing = bool(getattr(cfg, "testing", False))

    try:
        db_path = _text_or_default(getattr(cfg, "sessions_db_path", None))
        if not db_path:
            raise FileNotFoundError("sessions_db_path not configured")

        def _ping_db(path: str) -> None:
            from pathlib import Path

            file_path = Path(path)
            if not file_path.exists():
                raise FileNotFoundError(file_path)
            conn = sqlite3.connect(f"file:{file_path.as_posix()}?mode=ro", uri=True, timeout=1.0)
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()

        await anyio.to_thread.run_sync(_ping_db, db_path)
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "skipped" if testing else "error"

    # Check LLM provider
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

    coordination = {}
    try:
        coordinator = getattr(request.app.state, "node_coordinator", None)
        if coordinator is not None:
            snapshot = coordinator.snapshot()
            coordination = {
                "node_id": _text_or_default(snapshot.get("node_id"), _text_or_default(getattr(cfg, "node_id", None), "")),
                "role": _text_or_default(snapshot.get("role"), _text_or_default(getattr(cfg, "node_role", None), "secondary")),
                "has_recent_primary": snapshot.get("has_recent_primary"),
                "peer_count": len(snapshot.get("peers", [])),
            }
        else:
            coordination = {
                "node_id": _text_or_default(getattr(cfg, "node_id", None), ""),
                "role": _text_or_default(getattr(cfg, "node_role", None), "secondary"),
                "has_recent_primary": None,
                "peer_count": 0,
            }
    except Exception:
        coordination = {
            "node_id": _text_or_default(getattr(cfg, "node_id", None), ""),
            "role": _text_or_default(getattr(cfg, "node_role", None), "secondary"),
            "has_recent_primary": None,
            "peer_count": 0,
        }

    memory = {}
    failover = {}
    try:
        queue = getattr(request.app.state, "memory_write_queue", None)
        lease_manager = getattr(request.app.state, "memory_lease_manager", None)
        coordinator = getattr(request.app.state, "node_coordinator", None)
        failover_state = getattr(request.app.state, "failover_state", None)
        coord_snapshot = coordinator.snapshot() if coordinator is not None else {}
        if not isinstance(coord_snapshot, dict):
            coord_snapshot = {}
        lease_snapshot = lease_manager.snapshot() if lease_manager else None
        if lease_snapshot is not None and not hasattr(lease_snapshot, "to_dict"):
            lease_snapshot = None
        node_role = _text_or_default(getattr(cfg, "node_role", None), "secondary")
        sync = {
            "role": _text_or_default(coord_snapshot.get("role"), node_role),
            "is_primary": bool(coordinator is not None and getattr(coordinator, "role", "") == "primary"),
            "has_recent_primary": _bool_or_default(coord_snapshot.get("has_recent_primary", False), False),
            "memory_is_fresh": _bool_or_default(coord_snapshot.get("memory_is_fresh", True), True),
            "last_memory_revision": _float_or_default(coord_snapshot.get("last_memory_revision", 0.0), 0.0),
            "last_memory_sync": _float_or_default(coord_snapshot.get("last_memory_sync", 0.0), 0.0),
        }
        memory = {
            "queue_size": len(queue) if queue is not None else 0,
            "queue_pending": queue.snapshot() if queue is not None else [],
            "lease": lease_snapshot.to_dict() if lease_snapshot else None,
            "freshness": {
                "last_revision": _float_or_default(coord_snapshot.get("last_memory_revision", 0.0), 0.0),
                "last_sync": _float_or_default(coord_snapshot.get("last_memory_sync", 0.0), 0.0),
                "is_fresh": _bool_or_default(coord_snapshot.get("memory_is_fresh", True), True),
            },
        }
        failover = failover_state.snapshot() if failover_state is not None else {}
        if not isinstance(failover, dict):
            failover = {}
    except Exception:
        sync = {
            "role": node_role,
            "is_primary": False,
            "has_recent_primary": False,
            "memory_is_fresh": True,
            "last_memory_revision": 0.0,
            "last_memory_sync": 0.0,
        }
        memory = {
            "queue_size": 0,
            "queue_pending": [],
            "lease": None,
            "freshness": {"last_revision": 0.0, "last_sync": 0.0, "is_fresh": True},
        }
        failover = {
            "required_misses": 2,
            "miss_count": 0,
            "last_check_at": 0.0,
            "last_primary_seen_at": 0.0,
            "last_promotion_at": 0.0,
            "last_action": "idle",
            "last_reason": "",
            "promoted_role": "",
            "should_promote": False,
        }
    
    healthy_values = {"ok", "configured", "not_configured"}
    status = 200 if all(
        v in healthy_values
        or (testing and k == "database")
        or k in {"node_role", "cluster_name"}
        for k, v in checks.items()
    ) else 503
    payload = {
        "status": "ok" if status == 200 else "degraded",
        "checks": checks,
        "coordination": coordination,
        "memory": memory,
        "sync": sync,
        "failover": {
            "required_misses": _int_or_default(failover.get("required_misses", 2), 2),
            "miss_count": _int_or_default(failover.get("miss_count", 0), 0),
            "last_check_at": _float_or_default(failover.get("last_check_at", 0.0), 0.0),
            "last_primary_seen_at": _float_or_default(failover.get("last_primary_seen_at", 0.0), 0.0),
            "last_promotion_at": _float_or_default(failover.get("last_promotion_at", 0.0), 0.0),
            "last_action": _text_or_default(failover.get("last_action"), "idle"),
            "last_reason": _text_or_default(failover.get("last_reason"), ""),
            "promoted_role": _text_or_default(failover.get("promoted_role"), ""),
            "should_promote": _bool_or_default(failover.get("should_promote", False), False),
        },
    }
    return JSONResponse(payload, status_code=status)
