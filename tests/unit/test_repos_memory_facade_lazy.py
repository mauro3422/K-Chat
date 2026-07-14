from __future__ import annotations

import subprocess
import sys


def test_repos_memory_package_import_is_lazy() -> None:
    script = r"""
import importlib
import sys

repos_memory = importlib.import_module("src.memory.repos_memory")
print("src.memory.repos_memory.entity_repo" in sys.modules)
print("src.memory.repos_memory.memory_index_repo" in sys.modules)
print("src.memory.repos_memory.processing_catalog_repo" in sys.modules)
print("src.memory.repos_memory.work_catalog_repo" in sys.modules)
print("src.memory.repos_memory.container" in sys.modules)
from src.memory.repos_memory import MemoryRepositories, get_memory_repos
print(type(MemoryRepositories).__name__)
print("src.memory.repos_memory.entity_repo" in sys.modules)
print("src.memory.repos_memory.memory_index_repo" in sys.modules)
print("src.memory.repos_memory.processing_catalog_repo" in sys.modules)
print("src.memory.repos_memory.work_catalog_repo" in sys.modules)
print("src.memory.repos_memory.container" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "False",
        "False",
        "False",
        "False",
        "False",
        "type",
        "False",
        "False",
        "False",
        "False",
        "True",
    ]


def test_repos_package_import_is_lazy() -> None:
    script = r"""
import importlib
import sys

repos = importlib.import_module("src.memory.repos")
print("src.memory.repos.base" in sys.modules)
print("src.memory.repos.message_repository" in sys.modules)
print("src.memory.repos.session_repository" in sys.modules)
print("src.memory.repos.bundle" in sys.modules)
from src.memory.repos import MessageRecord, Repositories
print(type(MessageRecord).__name__)
print(type(Repositories).__name__)
print("src.memory.repos.base" in sys.modules)
print("src.memory.repos.message_repository" in sys.modules)
print("src.memory.repos.session_repository" in sys.modules)
print("src.memory.repos.bundle" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "False",
        "False",
        "False",
        "False",
        "type",
        "type",
        "True",
        "True",
        "False",
        "True",
    ]


def test_repos_bundle_import_is_lazy() -> None:
    script = r"""
import importlib
import sys

bundle = importlib.import_module("src.memory.repos.bundle")
print("src.memory.repos.debug_repository" in sys.modules)
print("src.memory.repos.message_repository" in sys.modules)
print("src.memory.repos.memory_index_repository" in sys.modules)
print("src.memory.repos.saved_widget_repository" in sys.modules)
print("src.memory.repos.session_repository" in sys.modules)
print("src.memory.repos.tool_call_repository" in sys.modules)
print("src.memory.repos.widget_state_repository" in sys.modules)
print(type(bundle.Repositories).__name__)
print(callable(bundle.get_repos))
print("src.memory.repos.debug_repository" in sys.modules)
print("src.memory.repos.message_repository" in sys.modules)
print("src.memory.repos.memory_index_repository" in sys.modules)
print("src.memory.repos.saved_widget_repository" in sys.modules)
print("src.memory.repos.session_repository" in sys.modules)
print("src.memory.repos.tool_call_repository" in sys.modules)
print("src.memory.repos.widget_state_repository" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "False",
        "False",
        "False",
        "False",
        "False",
        "False",
        "False",
        "type",
        "True",
        "False",
        "False",
        "False",
        "False",
        "False",
        "False",
        "False",
    ]


def test_repos_memory_container_import_is_lazy() -> None:
    script = r"""
import importlib
import sys

container = importlib.import_module("src.memory.repos_memory.container")
print("src.memory.repos_memory.entity_repo" in sys.modules)
print("src.memory.repos_memory.memory_index_repo" in sys.modules)
print("src.memory.repos_memory.processing_catalog_repo" in sys.modules)
print("src.memory.repos_memory.work_catalog_repo" in sys.modules)
print("src.memory.retrieval.hybrid_retriever" in sys.modules)
print("src.memory.vector.store" in sys.modules)
print(type(container.MemoryRepositories).__name__)
print(callable(container.get_memory_repos))
print("src.memory.repos_memory.entity_repo" in sys.modules)
print("src.memory.repos_memory.memory_index_repo" in sys.modules)
print("src.memory.repos_memory.processing_catalog_repo" in sys.modules)
print("src.memory.repos_memory.work_catalog_repo" in sys.modules)
print("src.memory.repos_memory.container" in sys.modules)
print("src.memory.retrieval.hybrid_retriever" in sys.modules)
print("src.memory.vector.store" in sys.modules)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    assert result.stdout.strip().splitlines() == [
        "False",
        "False",
        "False",
        "False",
        "False",
        "False",
        "type",
        "True",
        "False",
        "False",
        "False",
        "False",
        "True",
        "False",
        "False",
    ]


def test_memory_repositories_constructor_is_lazy(monkeypatch) -> None:
    from src.memory.repos_memory import container

    calls: list[str] = []

    class FakeVectorStore:
        def __init__(self, db_path: str) -> None:
            calls.append(f"vector:{db_path}")

        def close(self) -> None:
            calls.append("vector:close")

    class FakeEntityGraph:
        def __init__(self) -> None:
            calls.append("entity")

    class FakeHybridRetriever:
        def __init__(self, db_path: str) -> None:
            calls.append(f"hybrid:{db_path}")

        def close(self) -> None:
            calls.append("hybrid:close")

    class FakeWorkCatalog:
        def __init__(self, db_path: str) -> None:
            calls.append(f"work:{db_path}")

    class FakeProcessingCatalog:
        def __init__(self, db_path: str) -> None:
            calls.append(f"processing:{db_path}")

    monkeypatch.setattr(container, "_build_vector_store", lambda db_path: FakeVectorStore(db_path))
    monkeypatch.setattr(container, "_build_entity_graph", lambda: FakeEntityGraph())
    monkeypatch.setattr(container, "_build_hybrid_retriever", lambda db_path: FakeHybridRetriever(db_path))
    monkeypatch.setattr(container, "_build_work_catalog", lambda db_path: FakeWorkCatalog(db_path))
    monkeypatch.setattr(container, "_build_processing_catalog", lambda db_path: FakeProcessingCatalog(db_path))

    repos = container.MemoryRepositories(db_path="memory.db")

    assert calls == []
    assert repos._vector_store is None
    assert repos._entity_graph is None
    assert repos._hybrid_retriever is None
    assert repos._work_catalog is None
    assert repos._processing_catalog is None

    _ = repos.vector_store
    _ = repos.entity_graph
    _ = repos.hybrid_retriever
    _ = repos.work_catalog
    _ = repos.processing_catalog

    assert calls == [
        "vector:memory.db",
        "entity",
        "hybrid:memory.db",
        "work:memory.db",
        "processing:memory.db",
    ]


def test_memory_repositories_close_resets_cached_helpers(monkeypatch) -> None:
    from src.memory.repos_memory import container

    calls: list[str] = []

    class FakeVectorStore:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path
            self.closed = False
            calls.append(f"vector:{db_path}")

        def close(self) -> None:
            self.closed = True
            calls.append("vector:close")

    class FakeHybridRetriever:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path
            self.closed = False
            calls.append(f"hybrid:{db_path}")

        def close(self) -> None:
            self.closed = True
            calls.append("hybrid:close")

    class FakeEntityGraph:
        def __init__(self) -> None:
            calls.append("entity")

    class FakeWorkCatalog:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path
            calls.append(f"work:{db_path}")

    class FakeProcessingCatalog:
        def __init__(self, db_path: str) -> None:
            self.db_path = db_path
            calls.append(f"processing:{db_path}")

    monkeypatch.setattr(container, "_build_vector_store", lambda db_path: FakeVectorStore(db_path))
    monkeypatch.setattr(container, "_build_entity_graph", lambda: FakeEntityGraph())
    monkeypatch.setattr(container, "_build_hybrid_retriever", lambda db_path: FakeHybridRetriever(db_path))
    monkeypatch.setattr(container, "_build_work_catalog", lambda db_path: FakeWorkCatalog(db_path))
    monkeypatch.setattr(container, "_build_processing_catalog", lambda db_path: FakeProcessingCatalog(db_path))

    repos = container.MemoryRepositories(db_path="memory.db")

    first_vector = repos.vector_store
    first_entity_graph = repos.entity_graph
    first_hybrid = repos.hybrid_retriever
    first_work_catalog = repos.work_catalog
    first_processing_catalog = repos.processing_catalog

    repos.close()

    assert first_vector.closed is True
    assert first_hybrid.closed is True
    assert repos._vector_store is None
    assert repos._entity_graph is None
    assert repos._hybrid_retriever is None
    assert repos._work_catalog is None
    assert repos._processing_catalog is None

    second_vector = repos.vector_store
    second_entity_graph = repos.entity_graph
    second_hybrid = repos.hybrid_retriever
    second_work_catalog = repos.work_catalog
    second_processing_catalog = repos.processing_catalog

    assert second_vector is not first_vector
    assert second_entity_graph is not first_entity_graph
    assert second_hybrid is not first_hybrid
    assert second_work_catalog is not first_work_catalog
    assert second_processing_catalog is not first_processing_catalog
    assert calls == [
        "vector:memory.db",
        "entity",
        "hybrid:memory.db",
        "work:memory.db",
        "processing:memory.db",
        "vector:close",
        "hybrid:close",
        "vector:memory.db",
        "entity",
        "hybrid:memory.db",
        "work:memory.db",
        "processing:memory.db",
    ]


def test_memory_repositories_setters_close_replaced_cached_helpers() -> None:
    from src.memory.repos_memory import container

    class FakeVectorStore:
        def __init__(self, name: str) -> None:
            self.name = name
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeHybridRetriever:
        def __init__(self, name: str) -> None:
            self.name = name
            self.closed = False

        def close(self) -> None:
            self.closed = True

    repos = container.MemoryRepositories(db_path="memory.db")
    first_vector = FakeVectorStore("first")
    second_vector = FakeVectorStore("second")
    first_hybrid = FakeHybridRetriever("first")
    second_hybrid = FakeHybridRetriever("second")

    repos.vector_store = first_vector
    repos.vector_store = second_vector
    repos.hybrid_retriever = first_hybrid
    repos.hybrid_retriever = second_hybrid

    assert first_vector.closed is True
    assert second_vector.closed is False
    assert first_hybrid.closed is True
    assert second_hybrid.closed is False
    assert repos._vector_store is second_vector
    assert repos._hybrid_retriever is second_hybrid


def test_memory_repositories_close_keeps_closing_after_failure() -> None:
    from src.memory.repos_memory import container

    class FailingVectorStore:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True
            raise RuntimeError("vector close failed")

    class ClosingHybridRetriever:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    repos = container.MemoryRepositories(db_path="memory.db")
    vector_store = FailingVectorStore()
    hybrid_retriever = ClosingHybridRetriever()

    repos.vector_store = vector_store
    repos.hybrid_retriever = hybrid_retriever

    repos.close()

    assert vector_store.closed is True
    assert hybrid_retriever.closed is True
    assert repos._vector_store is None
    assert repos._hybrid_retriever is None
