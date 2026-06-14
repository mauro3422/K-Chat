"""Bootstrap module for database initialization.

This module breaks the circular dependency between connection_pool and schema
by providing a dedicated initialization entry point.
"""

from src.memory.lifecycle import ensure_initialized


async def ensure_db_initialized(db_path: str) -> None:
    """Ensure the database at the given path is initialized.

    This should be called once at application startup (lifespan, CLI main),
    not on every connection acquisition.
    """
    # Lazy import to avoid circular dependency: schema -> connection_pool -> bootstrap -> schema
    from src.memory.schema import init_db_for_path
    await ensure_initialized(db_path, init_db_for_path)
