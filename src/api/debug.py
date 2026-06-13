"""Debug operations."""

from typing import Any

from src.memory.repos import DebugRepository
from src.api.debug_contract import DebugOpsDeps


def _resolve_debug_deps(
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> DebugOpsDeps:
    if deps is not None:
        return deps
    return DebugOpsDeps(debug_repo=debug_repo)


def save_debug_info(
    session_id: str,
    data: dict[str, Any],
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> None:
    """Guarda información de depuración de una sesión."""
    _deps = _resolve_debug_deps(debug_repo=debug_repo, deps=deps)
    repo = _deps.debug_repo if _deps.debug_repo is not None else DebugRepository()
    return repo.save_info(session_id, data)


def get_debug_info(
    session_id: str,
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> dict[str, Any]:
    """Obtiene información de depuración de una sesión."""
    _deps = _resolve_debug_deps(debug_repo=debug_repo, deps=deps)
    repo = _deps.debug_repo if _deps.debug_repo is not None else DebugRepository()
    return repo.get_info(session_id)


def append_asr_telemetry(
    session_id: str,
    event: dict[str, Any],
    debug_repo: DebugRepository | None = None,
    deps: DebugOpsDeps | None = None,
) -> None:
    _deps = _resolve_debug_deps(debug_repo=debug_repo, deps=deps)
    repo = _deps.debug_repo if _deps.debug_repo is not None else DebugRepository()
    info = repo.get_info(session_id)
    telemetry = info.get("asr_telemetry") or []
    if not isinstance(telemetry, list):
        telemetry = []
    telemetry.append(event)
    if len(telemetry) > 100:
        telemetry = telemetry[-100:]
    info["asr_telemetry"] = telemetry
    repo.save_info(session_id, info)
