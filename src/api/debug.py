"""Debug operations."""

from typing import Any

from src.memory.repos import DebugRepository
from src.api.debug_contract import DebugOpsDeps
from src.api._resolve import resolve_deps


def _resolve_debug_deps(
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> DebugOpsDeps:
    return resolve_deps(deps, DebugOpsDeps, debug_repo=debug_repo)


async def save_debug_info(
    session_id: str,
    data: dict[str, Any],
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> None:
    """Save debug information for a session."""
    _deps = _resolve_debug_deps(debug_repo=debug_repo, deps=deps)
    repo = _deps.debug_repo if _deps.debug_repo is not None else DebugRepository()
    return await repo.save_info(session_id, data)


async def get_debug_info(
    session_id: str,
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> dict[str, Any]:
    """Get debug information for a session."""
    _deps = _resolve_debug_deps(debug_repo=debug_repo, deps=deps)
    repo = _deps.debug_repo if _deps.debug_repo is not None else DebugRepository()
    return await repo.get_info(session_id)


async def append_asr_telemetry(
    session_id: str,
    event: dict[str, Any],
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> None:
    _deps = _resolve_debug_deps(debug_repo=debug_repo, deps=deps)
    repo = _deps.debug_repo if _deps.debug_repo is not None else DebugRepository()
    info = await repo.get_info(session_id)
    telemetry = info.get("asr_telemetry") or []
    if not isinstance(telemetry, list):
        telemetry = []
    telemetry.append(event)
    if len(telemetry) > 100:
        telemetry = telemetry[-100:]
    info["asr_telemetry"] = telemetry
    await repo.save_info(session_id, info)
