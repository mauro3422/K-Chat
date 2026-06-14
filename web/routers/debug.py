import os
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from src.memory.repos import get_repos
from web.logging_handler import get_backend_logs

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/rate-limits")
async def rate_limits(request: Request) -> dict:
    _local_only(request)
    from src.llm.rate_limit_state import get_rate_limit_store
    return get_rate_limit_store().summary()


@router.get("/models/availability")
async def model_availability(request: Request) -> dict:
    """Return real-time availability for all discoverable models.

    Combines rate-limit state with known model tiers so the UI can
    show live availability dots.
    """
    _local_only(request)
    from src.llm.rate_limit_state import get_rate_limit_store
    from web.routers.pages import get_available_model_ids, _get_model_tier, get_available_models

    rl = get_rate_limit_store()
    from src.llm.model_registry import get_model_registry
    reg = get_model_registry()
    result: dict[str, dict] = {}

    for model_id in get_available_model_ids():
        tier = _get_model_tier(model_id)
        if tier == "zen":
            continue  # hide Zen from UI
        cooldown = rl.get_cooldown_remaining(model_id)
        if cooldown is not None:
            status = "rate_limited"
        elif rl.is_available(model_id):
            status = "available"
        elif rl.is_unavailable(model_id):
            status = "unavailable"
        else:
            status = "unknown"  # never tried since last restart
        result[model_id] = {
            "status": status,
            "tier": tier,
            "cooldown_remaining": cooldown,
        }

    reg_summary = reg.summary()
    return {
        "models": result,
        "limited_count": rl.summary()["limited_count"],
        "go_quota_exhausted": reg.is_quota_exhausted(),
        "total_models": reg_summary["total_models"],
        "tier_counts": reg_summary["tier_counts"],
    }


def _local_only(request: Request) -> None:
    if os.getenv("TESTING") == "true":
        return
    host = request.client.host if request.client else "unknown"
    if host in ("127.0.0.1", "::1", "localhost"):
        return
    logger.warning("Debug endpoint access denied from %s", host)
    raise HTTPException(status_code=403, detail="Debug endpoint disabled in production")


@router.get("/sessions/{session_id}/debug", dependencies=[Depends(_local_only)])
async def debug_info(session_id: str) -> JSONResponse:
    repos = get_repos()
    await repos.sessions.require_session(session_id)
    d = await repos.debug.get_info(session_id)
    return JSONResponse(d)


@router.get("/debug/backend-logs", dependencies=[Depends(_local_only)])
def backend_logs() -> JSONResponse:
    return JSONResponse({"logs": get_backend_logs()})
