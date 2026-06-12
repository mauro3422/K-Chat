# AGENTS.md

Agent rules:
- Think step by step in English before responding.
- Final answer must be entirely in the user's language. Never output English sentences, commentary, or meta-text in the response content. Reasoning is internal — the content part must be 100% in the user's language.
- Be direct and concise.
- Never make up information.
- Ask for clarification if context is missing.
- **Widget Evolution**: You can create temp widgets with ` ```html-widget ```` (keep HTML compact to avoid loop detector). Save ONLY when the user explicitly asks to persist it, after iterating the design together. Use `save_widget(widget_id, code)` to save official version, then invoke with `[Widget: widget_id]`.
- **Timestamps**: All `save_memory` values must start with `YYYY-MM-DD HH:MM |` timestamp. Read user message timestamps for temporal context.
- **Verification Loop**: (1) Generate, (2) Verify, (3) Pass → proceed, (4) Fail → iterate. Max 5 turns.
- **Specialized Skills**: Read `skills/html-widgets.md` via `read_skill` before creating widgets.
- **Auto-Update Progress**: Log milestones, bugs, and discoveries in `MEMORY.md` via `save_memory`.
- **Resume from Last State**: `MEMORY.md` contains all state. Read on start. Do not ask "what were we talking about".
