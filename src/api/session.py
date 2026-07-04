"""Session operations."""

import logging

from src.memory.repos import Repositories, SessionRepository


logger = logging.getLogger(__name__)
from src.api.session_contract import SessionOpsDeps
from src.api.exceptions import ServiceException
from src.api._resolve import resolve_deps


def _resolve_local_node_id() -> str:
    """Return the active coordinator's node_id, or '' when unconfigured.

    Injected here at the API layer (not in src/memory) to keep the
    storage module pure. The node_id stamps new sessions with
    ``origin_node_id`` so the federated merge can distinguish "session
    created on this node" vs "session synced from a peer".
    """
    try:
        from src.coordination.node_state import peek_node_coordinator
        coordinator = peek_node_coordinator()
        if coordinator is None:
            return ""
        return getattr(coordinator, "node_id", "") or ""
    except Exception:
        logger.warning("Failed to resolve local node_id")
        return ""


def _resolve_session_deps(
    session_repo: SessionRepository | None = None,
    repos: Repositories | None = None,
    deps: SessionOpsDeps | None = None,
) -> SessionOpsDeps:
    return resolve_deps(deps, SessionOpsDeps, session_repo=session_repo, repos=repos)


async def ensure_session(session_id: str, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> None:
    """Ensure a session exists in the database.

    Stamps ``origin_node_id`` with the local node_id on first insert so
    the federated session directory can tell where the session was born.
    Existing sessions are left untouched.
    """
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return await repo.ensure(session_id, origin_node_id=_resolve_local_node_id())


async def rename_session(session_id: str, name: str, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> None:
    """Rename an existing session."""
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return await repo.rename(session_id, name)


async def delete_session(
    session_id: str,
    *,
    repos: Repositories,
    session_repo: SessionRepository | None = None,
    deps: SessionOpsDeps | None = None,
) -> None:
    """Delete a session and all its associated child records."""
    _deps = _resolve_session_deps(session_repo=session_repo, repos=repos, deps=deps)
    repo = _deps.session_repo
    if repo is None:
        repo = _deps.repos.sessions if _deps.repos is not None else SessionRepository()
    return await repo.delete_cascade(session_id, repos=_deps.repos)


async def get_sessions(limit: int = 50, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> list:
    """Return the list of sessions ordered by last activity."""
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return await repo.get_all(limit)


async def _require_session(session_id: str, session_repo: SessionRepository | None = None) -> None:
    """Validate that a session exists. Raises 404 if not found."""
    if not session_id or not session_id.strip():
        raise ServiceException(status_code=404, detail="Session not found")
    repo = session_repo or SessionRepository()
    if not await repo.exists(session_id):
        raise ServiceException(status_code=404, detail="Session not found")
