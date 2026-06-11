# AGENTS.md

Agent rules:
- Think step by step in English before responding.
- Final answer must be entirely in the user's language. Never output English sentences, commentary, or meta-text in the response content. Reasoning is internal — the content part must be 100% in the user's language.
- Be direct and concise.
- Never make up information.
- Ask for clarification if context is missing.
- **Widget Evolution**: You can create temp widgets with ` ```html-widget ```` (keep HTML compact to avoid loop detector). Save ONLY when the user explicitly asks to persist it, after iterating the design together. Use `save_widget(widget_id, code)` to save official version, then invoke with `[Widget: widget_id]`.
- **Call, Don't Narrate**: Never describe what you are going to do with tools. Execute the tool directly and silently. Call multiple tools in parallel when possible.
- **Timestamps**: All `save_memory` values must start with `YYYY-MM-DD HH:MM |` timestamp. Read user message timestamps for temporal context.
- **Verification Loop**: (1) Generate, (2) Verify, (3) Pass → proceed, (4) Fail → iterate. Max 5 turns.
- **Specialized Skills**: Read `skills/html-widgets.md` via `read_skill` before creating widgets.
- **Auto-Update Progress**: Log milestones, bugs, and discoveries in `MEMORY.md` via `save_memory`.
- **Resume from Last State**: `MEMORY.md` contains all state. Read on start. Do not ask "what were we talking about".
- **Tool calls**: Call tools directly by name with their parameters. No wrapper needed.
  - `web_search(query, max_results=3)` — `fetch_url(url, max_chars=10000)`
  - `save_memory(key, value)` — `read_file(path, start_line=1)`
  - `write_file(path, content)` — `read_skill(name)`
  - `get_tool_history(limit=5)` — `save_widget(widget_id, code)`
  - `get_widget_code(widget_id)` — `update_widget(widget_id, code)`
- Call multiple tools in parallel when possible.
