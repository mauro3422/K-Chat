"""Database initialization and ID generation."""


from src.memory.connection import get_conn as _get_conn
from src.memory.schema import init_db as _init_db
from src.core.orchestrator import generate_session_id as _generate_session_id


def init_db() -> None:
    """Inicializa la base de datos y ejecuta migraciones pendientes."""
    return _init_db()


def generate_session_id() -> str:
    """Genera un ID único de sesión."""
    return _generate_session_id()


def check_db_connection() -> bool:
    """Check that the database is reachable by running SELECT 1."""
    try:
        conn = _get_conn()
        conn.execute("SELECT 1")
        return True
    except Exception:
        return False
