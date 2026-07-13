"""Memory.db repository bundle and default constructor."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.memory.repos_memory.entity_repo import EntityRepository
    from src.memory.repos_memory.memory_index_repo import GlobalMemoryIndexRepository
    from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository
    from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository
    from src.memory.retrieval.hybrid_retriever import HybridRetriever
    from src.memory.vector.store import VectorStore


def _build_global_memory_index_repository() -> GlobalMemoryIndexRepository:
    from src.memory.repos_memory.memory_index_repo import GlobalMemoryIndexRepository

    return GlobalMemoryIndexRepository()


def _build_vector_store(db_path: str) -> "VectorStore":
    from src.memory.vector.store import VectorStore

    return VectorStore(db_path)


def _build_entity_graph() -> "EntityRepository":
    from src.memory.repos_memory.entity_repo import EntityRepository

    return EntityRepository()


def _build_hybrid_retriever(db_path: str) -> "HybridRetriever":
    from src.memory.retrieval.hybrid_retriever import HybridRetriever

    return HybridRetriever(db_path)


def _build_work_catalog(db_path: str) -> "MemoryWorkCatalogRepository":
    from src.memory.repos_memory.work_catalog_repo import MemoryWorkCatalogRepository

    return MemoryWorkCatalogRepository(db_path)


def _build_processing_catalog(db_path: str) -> "MemoryProcessingCatalogRepository":
    from src.memory.repos_memory.processing_catalog_repo import MemoryProcessingCatalogRepository

    return MemoryProcessingCatalogRepository(db_path)


class MemoryRepositories:
    """Container for all memory.db repositories.

    The lightweight memory index repository is ready immediately, while the
    heavier sqlite-backed helpers are built lazily on first access. This keeps
    bundle creation cheap for code paths that only need a subset of memory.db.
    """

    def __init__(
        self,
        *,
        memory_index: "GlobalMemoryIndexRepository" | None = None,
        db_path: str | None = None,
        vector_store: "VectorStore" | None = None,
        entity_graph: "EntityRepository" | None = None,
        hybrid_retriever: "HybridRetriever" | None = None,
        work_catalog: "MemoryWorkCatalogRepository" | None = None,
        processing_catalog: "MemoryProcessingCatalogRepository" | None = None,
    ) -> None:
        self.memory_index = memory_index or _build_global_memory_index_repository()
        self._db_path = db_path
        self._vector_store = vector_store
        self._entity_graph = entity_graph
        self._hybrid_retriever = hybrid_retriever
        self._work_catalog = work_catalog
        self._processing_catalog = processing_catalog

    def _resolve_db_path(self) -> str:
        if self._db_path is not None:
            return self._db_path
        from src.memory.memory_db_path import resolve_memory_db_path

        self._db_path = resolve_memory_db_path()
        return self._db_path

    @property
    def vector_store(self) -> "VectorStore":
        if self._vector_store is None:
            self._vector_store = _build_vector_store(self._resolve_db_path())
        return self._vector_store

    @vector_store.setter
    def vector_store(self, value: "VectorStore" | None) -> None:
        self._vector_store = value

    @property
    def entity_graph(self) -> "EntityRepository":
        if self._entity_graph is None:
            self._entity_graph = _build_entity_graph()
        return self._entity_graph

    @entity_graph.setter
    def entity_graph(self, value: "EntityRepository" | None) -> None:
        self._entity_graph = value

    @property
    def hybrid_retriever(self) -> "HybridRetriever":
        if self._hybrid_retriever is None:
            self._hybrid_retriever = _build_hybrid_retriever(self._resolve_db_path())
        return self._hybrid_retriever

    @hybrid_retriever.setter
    def hybrid_retriever(self, value: "HybridRetriever" | None) -> None:
        self._hybrid_retriever = value

    @property
    def work_catalog(self) -> "MemoryWorkCatalogRepository":
        if self._work_catalog is None:
            self._work_catalog = _build_work_catalog(self._resolve_db_path())
        return self._work_catalog

    @work_catalog.setter
    def work_catalog(self, value: "MemoryWorkCatalogRepository" | None) -> None:
        self._work_catalog = value

    @property
    def processing_catalog(self) -> "MemoryProcessingCatalogRepository":
        if self._processing_catalog is None:
            self._processing_catalog = _build_processing_catalog(self._resolve_db_path())
        return self._processing_catalog

    @processing_catalog.setter
    def processing_catalog(self, value: "MemoryProcessingCatalogRepository" | None) -> None:
        self._processing_catalog = value

    def close(self) -> None:
        """Close cached resources owned by this repository bundle."""
        for attr_name in ("_vector_store", "_hybrid_retriever"):
            resource: Any = getattr(self, attr_name, None)
            if resource is None:
                continue
            close = getattr(resource, "close", None)
            if callable(close):
                close()
            # Drop the cached handle so a later access rebuilds a fresh helper.
            setattr(self, attr_name, None)


def get_memory_repos() -> MemoryRepositories:
    """Create a MemoryRepositories instance with default repos."""
    return MemoryRepositories()
