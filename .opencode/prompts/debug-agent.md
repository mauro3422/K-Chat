# Debug Agent — Opencode-specific instructions

These instructions apply ONLY to the opencode debug agent (you), NOT to Kairos.

## Execution Style
- **Call, Don't Narrate**: Never describe what you are going to do with tools. Execute the tool directly and silently. Call multiple tools in parallel when possible.
- **Tool calls**: Call tools directly by name with their parameters. No wrapper needed.
  - `web_search(query, max_results=3)` — `fetch_url(url, max_chars=10000)`
  - `save_memory(key, value)` — `read_file(path, start_line=1)`
  - `write_file(path, content)` — `read_skill(name)`
  - `get_tool_history(limit=5)` — `save_widget(widget_id, code)`
  - `get_widget_code(widget_id)` — `update_widget(widget_id, code)`

## DB Direct Access
All session data persists in `memory/kairos_memory.db` (SQLite). Query it directly instead of asking the user for logs.
- `sqlite3 memory/kairos_memory.db "SELECT ..."` — session messages, debug_info, widgets, tool_calls
- `curl localhost:8000/sessions/{id}/debug` — debug info via API
- `curl localhost:8000/api/logs?level=E` — server errors
- See `.opencode/skills/db-query/SKILL.md` for ready-to-use queries
- Or use `scripts/db.sh search <term>`, `scripts/db.sh recent`, etc.

## Session Data
- `messages` table: full conversation history per session
- `debug_info` table: model, reasoning, tool_calls per session
- `tool_calls` table: individual tool call records
- `widget_states` table: widget state per session
- `saved_widgets` table: officially saved widgets (global)
- `memory_index` table: custom key-value lookups per session
- JSONL logs in `logs/server/` and `logs/client/` for structured debugging
