import os
import tempfile
import pytest
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.memory import init_db

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Fixture para crear y limpiar una base de datos SQLite aislada y limpia para cada test."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test.db")
    monkeypatch.setenv("MEMORY_DB_PATH", db_path)
    
    # Inicializar la base de datos para este test específico
    init_db()
    
    yield db_path
    
    # Limpieza del archivo de base de datos y su directorio temporal
    try:
        import sqlite3
        # Cerrar conexiones SQLite activas en este hilo (si las hubiera en cache/pool)
        # para evitar problemas de bloqueo en Windows
    except ImportError:
        pass
    
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
        os.rmdir(temp_dir)
    except Exception:
        pass
