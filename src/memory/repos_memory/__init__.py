"""Repositories for memory.db (curated, syncable memory).

These repos connect to memory.db, not sessions.db. They store global memory
(key-value facts, future embeddings, knowledge graph) that gets synced
across devices via Syncthing.
"""

from dataclasses import dataclass, field

from src.memory.repos_memory.memory_index_repo import GlobalMemoryIndexRepository


@dataclass
class MemoryRepositories:
    """Container for all memory.db repositories."""
    memory_index: GlobalMemoryIndexRepository = field(default_factory=GlobalMemoryIndexRepository)


def get_memory_repos() -> MemoryRepositories:
    """Create a MemoryRepositories instance with default repos."""
    return MemoryRepositories()


__all__ = [
    "GlobalMemoryIndexRepository",
    "MemoryRepositories",
    "get_memory_repos",
]
