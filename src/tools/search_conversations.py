"""Search across ALL session conversations in sessions.db (local).

Like grep for conversations. Searches the raw messages table and shows
matches with context (surrounding messages), grouped by session.
Useful when you don't remember which session had that info.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFINITION: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "search_conversations",
        "description": "Busca como grep en TODAS las conversaciones de sessions.db. Muestra las líneas donde aparece el texto con contexto alrededor (mensajes anteriores/posteriores). Útil para encontrar algo que se dijo sin recordar la sesión exacta.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en los mensajes. Si querés buscar frase exacta, ponela entre comillas."
                },
                "role": {
                    "type": "string",
                    "description": "Filtrar por rol del mensaje: 'user', 'assistant', o 'all' (default: 'all')",
                    "enum": ["all", "user", "assistant"],
                    "default": "all"
                },
                "context": {
                    "type": "integer",
                    "description": "Mensajes de contexto alrededor de cada match (como grep -C). Default: 1, max: 3",
                    "default": 1
                },
                "max_matches": {
                    "type": "integer",
                    "description": "Máximo total de matches a mostrar (default: 20, max: 50)",
                    "default": 20
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Si True, busca exactamente como se escribió (default: False = ignora mayúsculas)",
                    "default": False
                }
            },
            "required": ["query"]
        }
    }
}


async def run(**kwargs) -> str:
    query = (kwargs.get("query") or "").strip()
    role_filter = kwargs.get("role", "all")
    context_lines = min(int(kwargs.get("context", 1)), 3)
    max_matches = min(int(kwargs.get("max_matches", 20)), 50)
    case_sensitive = kwargs.get("case_sensitive", False)
    _repos = kwargs.get("_repos")

    if not query:
        return "[ERROR] La búsqueda no puede estar vacía."
    if _repos is None:
        return "[ERROR] Repositorios no disponibles."

    try:
        conn = await _repos.messages._get_conn()

        # Get all messages ordered by session and time
        role_sql = ""
        if role_filter != "all":
            role_sql = f"AND m.role = '{role_filter}'"

        cursor = await conn.execute(
            f"""SELECT m.id, m.session_id, m.role, m.content, m.created_at, s.name as session_name
               FROM messages m
               LEFT JOIN sessions s ON m.session_id = s.session_id
               WHERE 1=1 {role_sql}
               ORDER BY m.session_id, m.id ASC""",
        )
        all_rows = await cursor.fetchall()
        await conn.close()

        if not all_rows:
            return "[OK] No hay mensajes en sessions.db todavía."

        # Group messages by session
        sessions: dict[str, dict] = {}
        for row in all_rows:
            sid = row["session_id"]
            if sid not in sessions:
                sessions[sid] = {
                    "name": row["session_name"] or sid[:12],
                    "msgs": [],
                }
            sessions[sid]["msgs"].append({
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"][:19] if row["created_at"] else "",
            })

        # Search: find matches with context
        pattern = re.compile(re.escape(query), re.IGNORECASE if not case_sensitive else 0)
        match_count = 0
        output_lines: list[str] = []
        session_match_count: dict[str, int] = {}

        for sid, sdata in sessions.items():
            msgs = sdata["msgs"]
            # Track which message indices match
            match_indices = set()
            for i, msg in enumerate(msgs):
                if pattern.search(msg["content"]):
                    match_indices.add(i)
                    session_match_count[sid] = session_match_count.get(sid, 0) + 1

            if not match_indices:
                continue

            # Build context groups: merge overlapping contexts
            context_groups: list[set[int]] = []
            sorted_indices = sorted(match_indices)
            for idx in sorted_indices:
                start = max(0, idx - context_lines)
                end = min(len(msgs) - 1, idx + context_lines)
                block = set(range(start, end + 1))

                if context_groups and block.intersection(context_groups[-1]):
                    context_groups[-1].update(block)
                else:
                    context_groups.append(block)

            # Render each context group
            for group in context_groups:
                group_sorted = sorted(group)
                # Count new matches in this group
                group_matches = [i for i in group_sorted if i in match_indices]
                if match_count >= max_matches:
                    break

                # Render match header
                first_idx = group_sorted[0]
                last_idx = group_sorted[-1]
                lines_in_group = 0
                for i in group_sorted:
                    if match_count >= max_matches:
                        break

                    msg = msgs[i]
                    is_match = i in match_indices
                    icon = "🧑" if msg["role"] == "user" else "🤖"

                    # Mark matched line with > (like grep context marker)
                    if is_match:
                        prefix = f"> {icon}"
                    else:
                        prefix = f"  {icon}"

                    content = msg["content"]
                    # Truncate long messages
                    if len(content) > 300:
                        content = content[:297] + "..."

                    # Add a marker showing the match
                    if is_match:
                        # Find the match position for visual marker
                        match_obj = pattern.search(content)
                        if match_obj and len(content) < 300:
                            start_m = max(0, match_obj.start() - 30)
                            end_m = min(len(content), match_obj.end() + 30)
                            excerpt = content[start_m:end_m]
                            if start_m > 0:
                                excerpt = "..." + excerpt
                            if end_m < len(content):
                                excerpt = excerpt + "..."
                            lines_in_group += 1
                            if lines_in_group == 1:
                                output_lines.append(f"  📁 **{sdata['name']}**  `{sid[:12]}...`")
                            output_lines.append(
                                f"    {prefix} **{msg['created_at']}**  `{excerpt}`"
                            )
                        else:
                            lines_in_group += 1
                            if lines_in_group == 1:
                                output_lines.append(f"  📁 **{sdata['name']}**  `{sid[:12]}...`")
                            output_lines.append(
                                f"    {prefix} **{msg['created_at']}**  {content[:200]}"
                            )
                    else:
                        # Context line (non-matching)
                        output_lines.append(
                            f"    {prefix} **{msg['created_at']}**  {content[:150]}"
                        )

                    if is_match:
                        match_count += 1

                if match_count >= max_matches:
                    break
                # Add blank line between context groups
                output_lines.append("")

            if match_count >= max_matches:
                break

        if not match_count:
            return f"[OK] No se encontraron mensajes con '{query}' en ninguna sesión."

        # Summary header
        total_sessions = len(session_match_count)
        total_matches = sum(session_match_count.values())
        summary = f"🔍 **{total_matches} ocurrencias** de '{query}' en **{total_sessions} sesiones**:"
        if match_count < total_matches:
            summary += f" (mostrando {match_count}, usá max_matches más grande para ver más)"

        output_lines.insert(0, "")
        output_lines.insert(0, summary)

        return "\n".join(output_lines)

    except Exception as e:
        logger.exception("search_conversations failed")
        return f"[ERROR] Error al buscar en conversaciones: {e}"
