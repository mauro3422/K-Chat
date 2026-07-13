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
