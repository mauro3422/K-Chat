"""Resolve the sessions.db path (local, non-synced database)."""

import os


def resolve_db_path(config=None) -> str:
    """Return the path to sessions.db (local per-device database)."""
    if config is None:
        from src.config_loader import load_config
        config = load_config()
    return os.environ.get("SESSIONS_DB_PATH", config.sessions_db_path)
