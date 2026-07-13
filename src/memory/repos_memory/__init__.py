"""Lightweight facade for memory.db repositories.

Import concrete repository modules directly when you need them. The bundle
constructor is loaded lazily to keep package import cost low.
"""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "EntityRepository",
    "GlobalMemoryIndexRepository",
    "MemoryProcessingCatalogRepository",
    "MemoryWorkCatalogRepository",
    "MemoryRepositories",
    "get_memory_repos",
]

_LAZY_EXPORTS = {
    "EntityRepository": ("src.memory.repos_memory.entity_repo", "EntityRepository"),
    "GlobalMemoryIndexRepository": ("src.memory.repos_memory.memory_index_repo", "GlobalMemoryIndexRepository"),
    "MemoryProcessingCatalogRepository": ("src.memory.repos_memory.processing_catalog_repo", "MemoryProcessingCatalogRepository"),
    "MemoryWorkCatalogRepository": ("src.memory.repos_memory.work_catalog_repo", "MemoryWorkCatalogRepository"),
    "MemoryRepositories": ("src.memory.repos_memory.container", "MemoryRepositories"),
    "get_memory_repos": ("src.memory.repos_memory.container", "get_memory_repos"),
}


def __getattr__(name: str):
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
