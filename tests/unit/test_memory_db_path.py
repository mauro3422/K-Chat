from pathlib import Path

from src.config_loader import Config
from src.memory.memory_db_path import resolve_memory_db_path


def test_curated_memory_never_reuses_sessions_database(tmp_path, monkeypatch):
    monkeypatch.delenv("KAIROS_MEMORY_DB_PATH", raising=False)
    shared = tmp_path / "kairos_memory.db"
    config = Config(sessions_db_path=str(shared), memory_db_path=str(shared))

    resolved = Path(resolve_memory_db_path(config))

    assert resolved != shared.resolve()
    assert resolved.name == "kairos_curated_memory.db"
