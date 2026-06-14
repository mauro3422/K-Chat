"""Shared dependency resolution helpers for API operations."""
from __future__ import annotations

from typing import Callable, TypeVar

D = TypeVar("D")


def resolve_deps(
    deps: D | None,
    factory: Callable[..., D],
    **kwargs,
) -> D:
    """Resolve DI: return deps if provided, otherwise build from factory."""
    if deps is not None:
        return deps
    return factory(**kwargs)
