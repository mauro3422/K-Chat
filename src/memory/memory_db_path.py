"""Resolve the memory.db path (the curated, syncable database).

Uses KAIROS_MEMORY_DB_PATH env var (separate from MEMORY_DB_PATH / SESSIONS_DB_PATH
which are for sessions.db).
"""

import os
from pathlib import Path


def resolve_memory_db_path(config=None) -> str:
    """Return the path to memory.db (curated memory, synced between devices).

    Priority:
    1. KAIROS_MEMORY_DB_PATH env var
    2. config.memory_db_path (from .env file MEMORY_DB_PATH or default)
    """
    env_path = os.environ.get("KAIROS_MEMORY_DB_PATH")
    if env_path:
        return env_path

    if config is None:
        from src.config_loader import load_config
        config = load_config()

    memory_path = Path(config.memory_db_path).resolve()
    sessions_path = Path(config.sessions_db_path).resolve()
    if memory_path == sessions_path:
        return str(memory_path.with_name("kairos_curated_memory.db"))
    return str(memory_path)
