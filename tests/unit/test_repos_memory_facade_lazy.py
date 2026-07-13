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
        "True",
        "True",
        "True",
        "True",
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
        "True",
        "True",
    ]
