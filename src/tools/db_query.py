import logging
import sqlite3
from typing import Any

logger = logging.getLogger(__name__)

# Whitelist de tablas permitidas (solo lectura)
ALLOWED_TABLES = frozenset({
    "messages", "sessions", "tool_calls", "saved_widgets",
    "widget_states", "debug_info", "memory_index", "widget_versions",
})

# Columnas por defecto por tabla (las más útiles para debug)
DEFAULT_COLUMNS = {
    "messages": "id, session_id, role, substr(content,1,80) as content, created_at, model",
    "sessions": "session_id, name, created_at",
    "tool_calls": "id, session_id, tool_name, status, turn, created_at",
    "saved_widgets": "widget_id, version, description, created_at",
    "widget_states": "session_id, widget_id, substr(state,1,60) as state, updated_at",
    "debug_info": "session_id, model, updated_at",
    "memory_index": "session_id, key, substr(value,1,80) as value, updated_at",
    "widget_versions": "widget_id, version, description, created_at",
}

# Columna de orden por defecto por tabla
DEFAULT_ORDER = {
    "messages": "id",
    "sessions": "created_at",
    "tool_calls": "created_at",
    "saved_widgets": "created_at",
    "widget_states": "updated_at",
    "debug_info": "updated_at",
    "memory_index": "updated_at",
    "widget_versions": "created_at",
}


def _get_db_path() -> str:
    from src.config_loader import DEFAULT_CONFIG
    import os
    return os.environ.get("MEMORY_DB_PATH", DEFAULT_CONFIG.memory_db_path)


DEFINITION = {
    "type": "function",
    "function": {
        "name": "db_query",
        "description": "Consulta la base de datos SQLite del sistema en modo solo lectura. "
                       "Útil para debuggear sesiones, mensajes, tools, widgets, etc. "
                       "Soporta filtrado por session_id, orden y límite.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": sorted(ALLOWED_TABLES),
                    "description": "Tabla a consultar"
                },
                "session_id": {
                    "type": "string",
                    "description": "Filtrar por session_id (opcional). "
                                   "Usar '%' como wildcard para búsqueda parcial."
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de filas a retornar (default: 10, max: 50)",
                    "default": 10
                },
                "order_by": {
                    "type": "string",
                    "description": "Columna para ordenar (default: auto según tabla)"
                },
                "order_dir": {
                    "type": "string",
                    "enum": ["ASC", "DESC"],
                    "description": "Dirección de orden (default: DESC)",
                    "default": "DESC"
                },
                "columns": {
                    "type": "string",
                    "description": "Columnas a mostrar separadas por coma (default: columnas útiles según tabla)"
                }
            },
            "required": ["table"]
        }
    }
}


def run(
    table: str,
    session_id: str | None = None,
    limit: int = 10,
    order_by: str = "",
    order_dir: str = "DESC",
    columns: str = "",
    **kwargs: Any,
) -> str:
    """Ejecuta una consulta SELECT de solo lectura sobre la DB."""
    # Validar tabla
    if table not in ALLOWED_TABLES:
        allowed = ", ".join(sorted(ALLOWED_TABLES))
        return f"[ERROR] Tabla '{table}' no permitida. Permitidas: {allowed}"

    # Sanitizar y validar parámetros
    limit = max(1, min(limit, 50))
    order_dir = "DESC" if order_dir.upper() != "ASC" else "ASC"
    order_col = (order_by.strip() or DEFAULT_ORDER.get(table, "rowid")).strip()

    # Validar que order_col sea alfanumérico + guión bajo (SQL injection safe)
    if not order_col.replace("_", "").isalnum():
        order_col = DEFAULT_ORDER.get(table, "rowid")

    # Seleccionar columnas
    cols = (columns.strip() or DEFAULT_COLUMNS.get(table, "*")).strip()
    # Validar que cols solo contenga nombres de columna seguros
    col_list = [c.strip().split(" as ")[0].strip() for c in cols.split(",")]
    for c in col_list:
        c_clean = c.replace("substr(", "").replace(",1,80)", "").replace("(", "").replace(")", "")
        if not c_clean.replace("_", "").isalnum():
            return f"[ERROR] Columna inválida en la consulta: {c}"

    try:
        db_path = _get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        query_parts = [f"SELECT {cols} FROM {table}"]

        # WHERE seguro con parámetros
        params: list[Any] = []
        if session_id:
            if "%" in session_id:
                query_parts.append("WHERE session_id LIKE ?")
                params.append(session_id)
            else:
                query_parts.append("WHERE session_id = ?")
                params.append(session_id)

        query_parts.append(f"ORDER BY {order_col} {order_dir}")
        query_parts.append("LIMIT ?")
        params.append(limit)

        query = " ".join(query_parts)
        logger.debug("db_query: %s params=%s", query, params)

        cur.execute(query, params)
        rows = cur.fetchall()

        if not rows:
            return f"[INFO] Sin resultados en '{table}'" + (f" para session_id='{session_id}'" if session_id else "")

        # Formatear como tabla
        headers = rows[0].keys()
        result_lines = []
        result_lines.append(f"📊 {table} ({len(rows)} filas)")
        result_lines.append(" | ".join(str(h) for h in headers))
        result_lines.append("-" * min(80, len(" | ".join(str(h) for h in headers))))

        for row in rows:
            vals = []
            for h in headers:
                v = row[h]
                if v is None:
                    vals.append("NULL")
                else:
                    s = str(v)
                    if len(s) > 60:
                        s = s[:57] + "..."
                    vals.append(s)
            result_lines.append(" | ".join(vals))

        result = "\n".join(result_lines)

        if len(result) > 30000:
            result = result[:29997] + "..."

        return result

    except sqlite3.OperationalError as e:
        return f"[ERROR] Error en la consulta: {e}"
    except Exception as e:
        logger.exception("db_query failed")
        return f"[ERROR] Error interno al consultar la base de datos: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass
