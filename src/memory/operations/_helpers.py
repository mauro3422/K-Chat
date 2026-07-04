from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
import os

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
        with open(path, encoding="utf-8", errors="replace") as f:
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
        elif line.startswith("#") or line.startswith("User:") or line.startswith("System:"):
            continue
        elif current_key is not None:
            memories[current_key] = "\n".join(current_lines).strip()
            current_key = None
            current_lines = []
    if current_key:
        memories[current_key] = "\n".join(current_lines).strip()
    return memories


def _read_memory_header(path: str) -> tuple[str, str]:
    user = ""
    system = ""
    try:
        with open(path, encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line.startswith("User:"):
                    user = line.split(":", 1)[1].strip()
                elif line.startswith("System:"):
                    system = line.split(":", 1)[1].strip()
                elif line.startswith("## Memories"):
                    break
    except FileNotFoundError:
        pass
    return user, system


def _write_memory_md(path: str, memories: dict[str, str]) -> None:
    """Write MEMORY.md from a {key: value} mapping."""
    user, system = _read_memory_header(path)
    lines: list[str] = [
        "# MEMORY.md\n",
        "\n",
        f"User: {user}\n",
        f"System: {system}\n",
        "\n",
        "## Memories\n",
    ]

    regular = {k: v for k, v in sorted(memories.items()) if not k.startswith("_archived:")}
    archived = {k: v for k, v in sorted(memories.items()) if k.startswith("_archived:")}

    for key, value in regular.items():
        lines.append(f"- **{key}**: {value}\n")

    if archived:
        lines.append("\n")
        lines.append("## Archived Memories\n")
        for key, value in archived.items():
            lines.append(f"- **{key}**: {value}\n")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(lines)
    try:
        os.replace(tmp, path)
    except OSError as e:
        logger.error("Failed to persist memory file (disk full?): %s", e)


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
