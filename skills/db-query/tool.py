import asyncio
import logging
import sqlite3
import os
from typing import Any

from src.config_loader import load_config

logger = logging.getLogger(__name__)

# ── Tablas de sessions.db ─────────────────────────────────────────────
SESSIONS_TABLES = frozenset({
    "messages", "sessions", "tool_calls", "saved_widgets",
    "widget_states", "debug_info", "widget_versions",
    "chat_journal", "gateway_log",
})

# ── Tablas de memory.db ────────────────────────────────────────────────
MEMORY_TABLES = frozenset({
    "memory_index",
})

# Columnas por defecto por tabla
DEFAULT_COLUMNS = {
    "messages": "id, session_id, role, substr(content,1,80) as content, created_at, model",
    "sessions": "session_id, name, created_at",
    "tool_calls": "id, session_id, tool_name, status, turn, created_at",
    "saved_widgets": "widget_id, version, description, created_at",
    "widget_states": "session_id, widget_id, substr(state,1,60) as state, updated_at",
    "debug_info": "session_id, model, updated_at",
    "widget_versions": "widget_id, version, description, created_at",
    "chat_journal": "id, session_id, user_msg, model, duration_ms, ts",
    "gateway_log": "id, ts, level, service, event",
    "memory_index": "key, substr(value,1,80) as value, updated_at",
}

# Columnas de texto por tabla (para búsqueda LIKE)
SEARCHABLE_COLUMNS = {
    "messages": ["content"],
    "sessions": ["name", "session_id"],
    "tool_calls": ["tool_name", "input"],
    "saved_widgets": ["widget_id", "description", "code"],
    "widget_states": ["state"],
    "debug_info": ["model", "reasoning"],
    "widget_versions": ["code", "description"],
    "chat_journal": ["user_msg", "assistant_msg", "error", "session_id"],
    "gateway_log": ["level", "service", "event", "detail"],
    "memory_index": ["key", "value"],
}

DEFAULT_ORDER = {
    "messages": "id",
    "sessions": "created_at",
    "tool_calls": "created_at",
    "saved_widgets": "updated_at",
    "widget_states": "updated_at",
    "debug_info": "updated_at",
    "widget_versions": "created_at",
    "chat_journal": "id",
    "gateway_log": "id",
    "memory_index": "updated_at",
}


def _get_db_path(db_name: str) -> str:
    """Resuelve la ruta de la base según el nombre: 'sessions' o 'memory'."""
    cfg = load_config()
    if db_name == "memory":
        return os.environ.get("KAIROS_MEMORY_DB_PATH", cfg.memory_db_path)
    # sessions por defecto (mantiene compatibilidad)
    return os.environ.get("SESSIONS_DB_PATH", cfg.sessions_db_path)


DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "db_query",
        "description": "Consulta SQLite del sistema en modo solo lectura. "
                       "Soporta sessions.db (chats, tools, widgets) y memory.db (memoria curada). "
                       "Ahora con búsqueda por contenido (search), filtros WHERE, y selección de base.",
        "parameters": {
            "type": "object",
            "properties": {
                "table": {
                    "type": "string",
                    "enum": sorted(SESSIONS_TABLES | MEMORY_TABLES),
                    "description": "Tabla a consultar. Según la tabla, se conecta a sessions.db o memory.db automáticamente."
                },
                "session_id": {
                    "type": "string",
                    "description": "Filtrar por session_id (opcional). Usar '%' como wildcard para búsqueda parcial."
                },
                "search": {
                    "type": "string",
                    "description": "Buscar texto en las columnas de contenido de la tabla (LIKE). Ej: 'sqlite', 'embeddings%'. No necesita '%' alrededor, se agrega automáticamente."
                },
                "where": {
                    "type": "string",
                    "description": "Filtro WHERE personalizado (opcional). Solo columnas simples y valores con ?, parámetros en where_params. Ej: 'role = ? AND content LIKE ?'"
                },
                "where_params": {
                    "type": "string",
                    "description": "Parámetros para el WHERE, separados por coma. Ej: 'user,%hola%'"
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
                    "description": "Columnas a mostrar separadas por coma (default: columnas útiles según tabla). Usar substr(col,1,N) para truncar."
                }
            },
            "required": ["table"]
        }
    }
}


def _is_memory_table(table: str) -> bool:
    """Determina si la tabla pertenece a memory.db."""
    return table in MEMORY_TABLES


def _validate_and_sanitize(
    table: str,
    session_id: str | None,
    search: str | None,
    where: str | None,
    where_params: str | None,
    limit: int,
    order_by: str,
    order_dir: str,
    columns: str,
) -> tuple[str | None, dict[str, Any]]:
    """Valida y sanitiza parámetros. Devuelve (error, params_dict)."""
    all_tables = SESSIONS_TABLES | MEMORY_TABLES
    if table not in all_tables:
        allowed = ", ".join(sorted(all_tables))
        return f"[ERROR] Tabla '{table}' no permitida. Permitidas: {allowed}", None

    limit = max(1, min(limit, 50))
    order_dir = "DESC" if order_dir.upper() != "ASC" else "ASC"
    order_col = (order_by.strip() or DEFAULT_ORDER.get(table, "rowid")).strip()

    if not order_col.replace("_", "").isalnum():
        order_col = DEFAULT_ORDER.get(table, "rowid")

    cols = (columns.strip() or DEFAULT_COLUMNS.get(table, "*")).strip()
    # Smart split: respeta paréntesis para substr(col, N, M)
    col_list_raw = []
    depth = 0
    current = []
    for ch in cols:
        if ch == '(':
            depth += 1
            current.append(ch)
        elif ch == ')':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            col_list_raw.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        col_list_raw.append(''.join(current).strip())
    
    for raw_c in col_list_raw:
        c_clean = raw_c.split(" as ")[0].strip() if " as " in raw_c else raw_c
        if c_clean.startswith("substr("):
            continue
        if not c_clean.replace("_", "").isalnum():
            return f"[ERROR] Columna inválida: '{c_clean}'", None
    for raw_c in col_list_raw:
        c_clean = raw_c.split(" as ")[0].strip() if " as " in raw_c else raw_c
        if c_clean.startswith("substr("):
            continue
        if not c_clean.replace("_", "").isalnum():
            return f"[ERROR] Columna inválida: '{c_clean}'", None

    # Sanitizar where param names
    where_safe = None
    if where:
        where_safe = where.strip()
        # Solo permitir palabras, ?, operadores comunes y espacios
        allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_? =!<>'%.,()ANDORLIKENOTIN ")
        for ch in where_safe:
            if ch not in allowed_chars:
                return f"[ERROR] Caracter no permitido en WHERE: '{ch}'", None

    # Parse where_params
    parsed_where_params: list[str] = []
    if where_params:
        parsed_where_params = [p.strip() for p in where_params.split(",")]

    return None, {
        "limit": limit,
        "order_dir": order_dir,
        "order_col": order_col,
        "cols": cols,
        "search": search.strip() if search else None,
        "where": where_safe,
        "where_params": parsed_where_params,
    }


def _format_rows_as_table(table: str, rows: list[Any]) -> str:
    """Formatea filas como tabla legible."""
    if not rows:
        return f"[INFO] Sin resultados en '{table}'"

    headers = rows[0].keys() if hasattr(rows[0], 'keys') else rows[0].keys()
    result_lines = [f"📊 {table} ({len(rows)} filas)"]
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


def _execute_query(table: str, session_id: str | None, params: dict[str, Any]) -> str:
    """Ejecuta la consulta SQL y formatea resultados."""
    db_name = "memory" if _is_memory_table(table) else "sessions"
    db_path = _get_db_path(db_name)
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        query_parts = [f"SELECT {params['cols']} FROM {table}"]
        query_params: list[Any] = []
        conditions: list[str] = []

        # Filtro por session_id
        if session_id:
            if "%" in session_id:
                conditions.append("session_id LIKE ?")
                query_params.append(session_id)
            else:
                conditions.append("session_id = ?")
                query_params.append(session_id)

        # Búsqueda por contenido (search)
        if params["search"]:
            searchable = SEARCHABLE_COLUMNS.get(table, [])
            if not searchable:
                return f"[ERROR] La tabla '{table}' no soporta búsqueda por contenido."
            # Construir: col1 LIKE ? OR col2 LIKE ? OR ...
            search_conditions = []
            for col in searchable:
                search_conditions.append(f"{col} LIKE ?")
                query_params.append(f"%{params['search']}%")
            conditions.append(f"({' OR '.join(search_conditions)})")

        # Filtro WHERE personalizado
        if params["where"]:
            conditions.append(f"({params['where']})")
            query_params.extend(params["where_params"])

        if conditions:
            query_parts.append("WHERE " + " AND ".join(conditions))

        query_parts.append(f"ORDER BY {params['order_col']} {params['order_dir']}")
        query_parts.append("LIMIT ?")
        query_params.append(params["limit"])

        query = " ".join(query_parts)
        logger.debug("db_query: %s params=%s", query, query_params)

        cur.execute(query, query_params)
        rows = cur.fetchall()

        if not rows:
            msg = f"[INFO] Sin resultados en '{table}'"
            if session_id:
                msg += f" para session_id='{session_id}'"
            return msg

        return _format_rows_as_table(table, rows)

    except sqlite3.OperationalError as e:
        return f"[ERROR] Error en la consulta: {e}"
    except Exception as e:
        logger.exception("db_query failed")
        return f"[ERROR] Error interno: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


async def run(
    table: str,
    session_id: str | None = None,
    search: str | None = None,
    where: str | None = None,
    where_params: str | None = None,
    limit: int = 10,
    order_by: str = "",
    order_dir: str = "DESC",
    columns: str = "",
    **kwargs: Any,
) -> str:
    """Ejecuta una consulta SELECT de solo lectura sobre la DB."""
    error, params = _validate_and_sanitize(
        table, session_id, search, where, where_params,
        limit, order_by, order_dir, columns,
    )
    if error:
        return error
    # Ejecutar la consulta SQLite en un thread para no bloquear el event loop
    return await asyncio.to_thread(_execute_query, table, session_id, params)
