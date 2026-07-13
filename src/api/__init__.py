"""Compatibilidad mínima para `src.api`.

Los consumidores nuevos deben importar submódulos concretos como
`src.api.orchestrator`, `src.api.repos`, `src.api.llm_client`, etc.
"""

from __future__ import annotations

from importlib import import_module

__all__ = ["get_repos"]


def __getattr__(name: str):
    if name == "get_repos":
        get_repos = import_module("src.api.repos").get_repos
        globals()[name] = get_repos
        return get_repos
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
