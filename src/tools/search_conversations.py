"""Search across ALL session conversations in sessions.db (local).

Full-text search over the raw messages table. Returns snippets from
matching messages grouped by session, with timestamps and context.
Useful when you don't remember which session had that info.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_conversations",
        "description": "Busca texto en TODAS las conversaciones de sessions.db (no en memoria curada). Sirve para encontrar algo que se dijo en alguna sesión pero no recordás cuál. Busca en los mensajes crudos del chat. Los resultados se agrupan por sesión.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en los mensajes (busca en user y assistant messages)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de resultados por sesión (default: 3, max: 10)",
                    "default": 3
                },
                "max_sessions": {
                    "type": "integer",
                    "description": "Máximo de sesiones a mostrar (default: 5, max: 10)",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    }
}


async def run(**kwargs) -> str:
    query = (kwargs.get("query") or "").strip()
    _repos = kwargs.get("_repos")
    limit = min(int(kwargs.get("limit", 3)), 10)
    max_sessions = min(int(kwargs.get("max_sessions", 5)), 10)

    if not query:
        return "[ERROR] La búsqueda no puede estar vacía."

    if _repos is None:
        return "[ERROR] Repositorios no disponibles."

    from src.memory.repos.message_repository import MessageRepository

    try:
        # Get all sessions first (with names)
        sessions_list = await _repos.sessions.get_all() if hasattr(_repos.sessions, 'get_all') else []

        # Search messages across all sessions using raw SQL through the message repo
        conn = await _repos.messages._get_conn()
        pattern = f"%{query}%"

        # Search in user messages and assistant messages
        cursor = await conn.execute(
            """SELECT m.session_id, m.role, m.content, m.created_at, s.name as session_name
               FROM messages m
               LEFT JOIN sessions s ON m.session_id = s.session_id
               WHERE m.content LIKE ?
               ORDER BY m.created_at DESC
               LIMIT ?""",
            (pattern, limit * max_sessions * 2),
        )
        rows = await cursor.fetchall()

        if not rows:
            return f"[OK] No se encontraron mensajes con '{query}' en ninguna sesión."

        # Group by session
        session_map: dict[str, dict] = {}
        for row in rows:
            sid = row["session_id"]
            if sid not in session_map:
                session_map[sid] = {
                    "name": row["session_name"] or sid[:12],
                    "messages": [],
                }
            if len(session_map[sid]["messages"]) < limit:
                session_map[sid]["messages"].append({
                    "role": row["role"],
                    "content": _truncate(row["content"], 200),
                    "created_at": row["created_at"][:19] if row["created_at"] else "",
                })

        # Sort sessions by most recent message
        sorted_sessions = sorted(session_map.items(), key=lambda x: x[1]["messages"][0]["created_at"], reverse=True)

        lines = [f"🔍 **{len(rows)} coincidencias** para '{query}' en {len(sorted_sessions)} sesiones:", ""]

        for sid, sdata in sorted_sessions[:max_sessions]:
            name = sdata["name"]
            lines.append(f"  📁 **{name}**  `{sid[:12]}...`")
            for msg in sdata["messages"]:
                icon = "🧑" if msg["role"] == "user" else "🤖"
                date = msg["created_at"]
                content = msg["content"]
                lines.append(f"    {icon} [{date}] {content}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        logger.exception("search_conversations failed")
        return f"[ERROR] Error al buscar en conversaciones: {e}"


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
