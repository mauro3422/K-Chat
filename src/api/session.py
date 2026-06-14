"""Session operations."""

from src.memory.repos import Repositories, SessionRepository
from src.api.session_contract import SessionOpsDeps
from src.api.exceptions import ServiceException


def _resolve_session_deps(
    session_repo: SessionRepository | None = None,
    repos: Repositories | None = None,
    deps: SessionOpsDeps | None = None,
) -> SessionOpsDeps:
    if deps is not None:
        return deps
    return SessionOpsDeps(
        session_repo=session_repo,
        repos=repos,
    )


async def ensure_session(session_id: str, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> None:
    """Ensure a session exists in the database."""
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return await repo.ensure(session_id)


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


async def _require_session(session_id: str) -> None:
    """Validate that a session exists. Raises 404 if not found."""
    if not session_id or not session_id.strip():
        raise ServiceException(status_code=404, detail="Session not found")
    repo = SessionRepository()
    if not await repo.exists(session_id):
        raise ServiceException(status_code=404, detail="Session not found")
