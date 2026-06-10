"""Lazy repository registry."""

from typing import Any

_repos: dict[str, Any] = {}


def _get_repo(cls: type, name: str) -> Any:
    if name not in _repos:
        _repos[name] = cls()
    return _repos[name]
