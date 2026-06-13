"""Session operations."""

from src.memory.repos import Repositories, SessionRepository
from src.api.session_contract import SessionOpsDeps


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


def ensure_session(session_id: str, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> None:
    """Asegura que una sesión exista en la base de datos."""
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return repo.ensure(session_id)


def rename_session(session_id: str, name: str, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> None:
    """Renombra una sesión existente."""
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return repo.rename(session_id, name)


def delete_session(
    session_id: str,
    *,
    repos: Repositories,
    session_repo: SessionRepository | None = None,
    deps: SessionOpsDeps | None = None,
) -> None:
    """Elimina una sesión y todos sus registros hijos asociados."""
    _deps = _resolve_session_deps(session_repo=session_repo, repos=repos, deps=deps)
    repo = _deps.session_repo
    if repo is None:
        repo = _deps.repos.sessions if _deps.repos is not None else SessionRepository()
    return repo.delete_cascade(session_id, repos=_deps.repos)


def get_sessions(limit: int = 50, session_repo: SessionRepository | None = None, deps: SessionOpsDeps | None = None) -> list:
    """Retorna la lista de sesiones ordenadas por última actividad."""
    _deps = _resolve_session_deps(session_repo=session_repo, deps=deps)
    repo = _deps.session_repo if _deps.session_repo is not None else SessionRepository()
    return repo.get_all(limit)
