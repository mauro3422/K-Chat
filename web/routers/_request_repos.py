"""Helpers for reading repository dependencies from request state."""

from __future__ import annotations

import inspect
from typing import Any

from fastapi import Request

from src.api.repos import get_repos


def is_unconfigured_mock(value: Any) -> bool:
    return type(value).__module__ == "unittest.mock"


def _has_async_session_repo(repos: Any) -> bool:
    sessions = getattr(repos, "sessions", None)
    if sessions is None:
        return False
    return inspect.iscoroutinefunction(getattr(sessions, "get_all", None))


def request_repos(request: Request | None, fallback=get_repos):
    app = getattr(request, "app", None)
    state = getattr(app, "state", None) if app is not None else None
    repos = getattr(state, "repos", None) if state is not None else None
    if repos is not None and _has_async_session_repo(repos):
        return repos
    return fallback()
