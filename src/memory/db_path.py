import os


def resolve_db_path(config=None) -> str:
    if config is None:
        from src.config_loader import load_config
        config = load_config()
    return os.environ.get("MEMORY_DB_PATH", config.memory_db_path)
