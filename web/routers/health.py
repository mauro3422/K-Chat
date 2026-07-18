from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from web.routers._node_helpers import _peer_cluster_state
from web.services.health_snapshot import (
    build_health_checks,
    build_health_coordination,
    build_health_runtime,
    checks_are_healthy,
)

router = APIRouter()


@router.get("/live")
async def live(request: Request):
    cfg = getattr(request.app.state, "config", None)
    return {
        "status": "ok",
        "node_id": getattr(cfg, "node_id", "") if cfg is not None else "",
        "role": getattr(cfg, "node_role", "") if cfg is not None else "",
    }


@router.get("/health")
async def health(request: Request):
    cfg = getattr(request.app.state, "config", None)
    checks = await build_health_checks(cfg, testing=bool(getattr(cfg, "testing", False)))
    testing = bool(getattr(cfg, "testing", False))

    coordination = {}
    try:
        coordinator = getattr(request.app.state, "node_coordinator", None)
        cluster = await _peer_cluster_state(request)
        if coordinator is not None:
            coordination = build_health_coordination(
                cfg=cfg,
                coordinator_snapshot=coordinator.snapshot(),
                cluster=cluster,
            )
        else:
            coordination = build_health_coordination(cfg=cfg, coordinator_snapshot=None, cluster=cluster)
    except Exception:
        coordination = build_health_coordination(cfg=cfg, coordinator_snapshot=None, cluster=None)

    memory = {}
    failover = {}
    try:
        queue = getattr(request.app.state, "memory_write_queue", None)
        lease_manager = getattr(request.app.state, "memory_lease_manager", None)
        coordinator = getattr(request.app.state, "node_coordinator", None)
        failover_state = getattr(request.app.state, "failover_state", None)
        coord_snapshot = coordinator.snapshot() if coordinator is not None else None
        lease_snapshot = lease_manager.snapshot() if lease_manager else None
        sync, memory, failover = build_health_runtime(
            cfg=cfg,
            coordinator_snapshot=coord_snapshot,
            coordinator_role=getattr(coordinator, "role", ""),
            queue_size=len(queue) if queue is not None else 0,
            queue_pending=queue.snapshot() if queue is not None else [],
            lease_snapshot=lease_snapshot,
            failover_snapshot=failover_state.snapshot() if failover_state is not None else None,
        )
    except Exception:
        sync, memory, failover = build_health_runtime(
            cfg=cfg,
            coordinator_snapshot=None,
            coordinator_role="",
            queue_size=0,
            queue_pending=[],
            lease_snapshot=None,
            failover_snapshot=None,
        )

    status = 200 if checks_are_healthy(checks, testing=testing) else 503
    payload = {
        "status": "ok" if status == 200 else "degraded",
        "checks": checks,
        "coordination": coordination,
        "memory": memory,
        "sync": sync,
        "failover": failover,
    }
    return JSONResponse(payload, status_code=status)
