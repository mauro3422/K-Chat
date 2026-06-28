"""Repositories for memory.db (curated, syncable memory).

These repos connect to memory.db, not sessions.db. They store global memory
(key-value facts, future embeddings, knowledge graph) that gets synced
across devices via Syncthing.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from src.memory.repos_memory.entity_repo import EntityRepository
from src.memory.repos_memory.memory_index_repo import GlobalMemoryIndexRepository
from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
from src.memory.retrieval.hybrid_retriever import HybridRetriever
from src.memory.vector.store import VectorStore


@dataclass
class MemoryRepositories:
    """Container for all memory.db repositories.

    Provides DI-ready access to memory.db operations. Tools receive
    this via ``_repos.memory`` instead of creating connections directly.
    """
    memory_index: GlobalMemoryIndexRepository = field(default_factory=GlobalMemoryIndexRepository)
    vector_store: Optional[VectorStore] = field(default=None)
    entity_graph: Optional[EntityRepository] = field(default=None)
    hybrid_retriever: Optional[HybridRetriever] = field(default=None)
    work_catalog: Optional[MemoryWorkCatalogRepository] = field(default=None)

    def __post_init__(self) -> None:
        from src.memory.memory_db_path import resolve_memory_db_path
        if self.vector_store is None:
            self.vector_store = VectorStore(resolve_memory_db_path())
        if self.entity_graph is None:
            self.entity_graph = EntityRepository()
        if self.hybrid_retriever is None:
            self.hybrid_retriever = HybridRetriever(resolve_memory_db_path())
        if self.work_catalog is None:
            self.work_catalog = MemoryWorkCatalogRepository(resolve_memory_db_path())


def get_memory_repos() -> MemoryRepositories:
    """Create a MemoryRepositories instance with default repos."""
    return MemoryRepositories()


__all__ = [
    "EntityRepository",
    "GlobalMemoryIndexRepository",
    "MemoryWorkCatalogRepository",
    "MemoryRepositories",
    "get_memory_repos",
]
