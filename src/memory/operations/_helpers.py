from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)


def _get_sessions_db() -> str:
    from src.memory.db_path import resolve_db_path
    return resolve_db_path()


def _get_memory_db() -> str:
    from src.memory.memory_db_path import resolve_memory_db_path
    return resolve_memory_db_path()


def _parse_memory_md(path: str) -> dict[str, str]:
    """Parse MEMORY.md into {key: value} dict."""
    memories: dict[str, str] = {}
    if not path:
        return memories
    try:
        with open(path) as f:
            content = f.read()
    except FileNotFoundError:
        return memories
    current_key: str | None = None
    current_lines: list[str] = []
    for line in content.split("\n"):
        if line.startswith("- **") and "**: " in line:
            if current_key:
                memories[current_key] = "\n".join(current_lines).strip()
            rest = line[4:]
            key_end = rest.index("**: ")
            current_key = rest[:key_end].strip()
            current_lines = [rest[key_end + 4:].strip()]
        elif line.startswith("- **") and "**:\n" in line.replace("\\n", "\n"):
            if current_key:
                memories[current_key] = "\n".join(current_lines).strip()
            current_key = line[4:line.index("**:")].strip()
            current_lines = [line[line.index("**:") + 3:].strip()]
        elif current_key:
            current_lines.append(line)
    if current_key:
        memories[current_key] = "\n".join(current_lines).strip()
    return memories


def _match_key_pattern(key: str, pattern: str) -> bool:
    if not pattern:
        return True
    if "*" in pattern:
        prefix = pattern.replace("*", "")
        return key.startswith(prefix)
    return key == pattern


def _get_memory_md_path() -> str:
    """Resolve MEMORY.md path."""
    import os
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "MEMORY.md")


@contextmanager
def _memory_db(repos=None):
    """Get memory.db connection, preferring DI repos connection."""
    if repos and repos.memory and repos.memory.vector_store:
        conn = repos.memory.vector_store._get_conn()
        should_close = False
    else:
        conn = sqlite3.connect(_get_memory_db())
        should_close = True
    try:
        yield conn
    finally:
        if should_close:
            conn.close()


@contextmanager
def _sessions_db(repos=None):
    """Get sessions.db connection (sync sqlite3)."""
    conn = sqlite3.connect(_get_sessions_db())
    try:
        yield conn
    finally:
        conn.close()
