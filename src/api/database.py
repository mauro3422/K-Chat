"""Database initialization and ID generation."""


from src.memory.database import init_db as _init_db
from src.core.orchestrator import generate_session_id as _generate_session_id


def init_db() -> None:
    """Inicializa la base de datos y ejecuta migraciones pendientes."""
    return _init_db()


def generate_session_id() -> str:
    """Genera un ID único de sesión."""
    return _generate_session_id()
