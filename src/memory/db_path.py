import os


def resolve_db_path(config=None) -> str:
    from src.config_loader import DEFAULT_CONFIG

    cfg = config or DEFAULT_CONFIG
    return os.environ.get("MEMORY_DB_PATH", cfg.memory_db_path)
