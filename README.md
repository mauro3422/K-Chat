# Kairos (K-Chat)

> **v0.0.21** — Personal minimalist agent with episodic memory, parallel tools, and web dashboard.
> No JS frameworks, no complex gateways. Each piece is an independent file.

## Vision

Kairos is not trying to be a copy of OpenClaw. It is born from the frustration of configuring a large platform, finding errors when trying to use it for real tasks, and wanting something more direct: a personal assistant that can chat, remember, use tools, show what it did, and iterate on its own project alongside the user.

The goal is not to have all channels, plugins, and layers from day one. The goal is to have a reliable and understandable core first: chat, memory, tools, streaming, debug, and the ability to evolve without fighting an opaque architecture. Future channels like Telegram, webhooks, or automations should be adapters around the same core, not a reason to turn the project into a bloated platform.

Kairos can take inspiration from OpenClaw ideas, but with a different priority: be a decent, stable, hackable, and well-built wrapper for a personal assistant, before becoming a huge ecosystem full of fragile pieces.

## Stack

- **Models:** big-pickle (default), deepseek-v4-flash-free (fallback) — OpenCode Zen API
- **Chat:** CLI + Web dashboard (FastAPI + vanilla JS + Jinja2)
- **Memory:** SQLite persistent (sessions, messages with reasoning, tool_calls with phases, debug_info)
- **Context:** SOUL.md + MEMORY.md + AGENTS.md + TOOLS.md (auto-created and auto-generated)
- **Frontend:** No build step, no bundles. HTML + CSS + JS vanilla (~2,000 lines total)

## Structure

```
├── config.py               → Reads .env, validates keys
├── SOUL.md / MEMORY.md     → Personality and user data (auto-created)
├── AGENTS.md / TOOLS.md    → Agent rules and tool guide (auto-generated)
├── src/
│   ├── api/                → Facade package for all DB operations
│   │   ├── __init__.py     → Public API (19+ functions)
│   │   ├── messages.py     → Message CRUD
│   │   ├── sessions.py     → Session management
│   │   ├── widgets.py      → Widget persistence
│   │   ├── debug.py        → Debug info
│   │   ├── tools.py        → Tool history
│   │   ├── rebuild.py      → History reconstruction
│   │   ├── filter.py       → UI message filtering
│   │   ├── stream.py       → Chat streaming
│   │   └── repos.py        → Repository singletons
│   ├── core/
│   │   ├── orchestrator.py → Chat loop, streaming, tool phases, compression
│   │   ├── tool_loop.py    → Sync + streaming tool execution loops
│   │   ├── chat_sync.py    → Non-streaming chat helper
│   │   └── history.py      → History reconstruction and UI filtering
│   ├── llm/
│   │   ├── protocol.py     → LLMProvider protocol definition
│   │   ├── openai_provider.py → OpenAI-compatible provider
│   │   ├── models.py       → API client, retry, model switching
│   │   ├── client.py       → chat() and chat_stream()
│   │   └── manager.py      → Model discovery, verification, selection
│   ├── memory/
│   │   ├── database.py     → SQLite connection + schema init
│   │   ├── repositories.py → CRUD repositories (messages, sessions, tools, widgets, debug)
│   │   └── migrations.py   → Schema migration functions
│   ├── tools/
│   │   ├── __init__.py     → Module exports
│   │   ├── loader.py       → Auto-loader (TOOL_MAP, TOOL_DEFINITIONS)
│   │   ├── runner.py       → Parallel tool execution
│   │   ├── web_search.py   → Web search via API
│   │   ├── fetch_url.py    → Fetch and extract web page content
│   │   ├── save_memory.py  → Persist data to MEMORY.md
│   │   ├── read_file.py    → Read project files
│   │   ├── write_file.py   → Write project files
│   │   ├── read_skill.py   → Load skills from skills/
│   │   ├── get_tool_history.py → Query tool usage
│   │   ├── save_widget.py  → Save widget to DB
│   │   ├── get_widget_code.py → Retrieve widget code
│   │   └── update_widget.py → Update widget version
│   ├── context.py          → System prompt builder, context loader
│   ├── compressor.py       → History compression via LLM
│   ├── background_tasks.py → Auto-rename sessions
│   ├── cli.py              → CLI entry point
│   ├── handler_cli.py      → CLI commands (/model, /clear, /help)
│   └── paths.py            → Path resolution utilities
├── web/
│   ├── server.py           → FastAPI app
│   ├── logging.py          → Backend log handler + ring buffer
│   ├── ui_utils.py         → HTML message renderer
│   ├── services/
│   │   ├── chat_stream.py  → Stream generator for web endpoint
│   │   └── message_renderer.py → Session message HTML renderer
│   ├── routers/
│   │   ├── chat.py         → Streaming POST endpoint
│   │   ├── pages.py        → HTML pages, sidebar, messages
│   │   ├── sessions.py     → Rename, delete
│   │   ├── widgets.py      → Widget API
│   │   └── debug.py        → Debug info, backend logs
│   ├── templates/          → Jinja2 templates
│   └── static/             → CSS, JS modules (chat, session, debug, widgets)
├── tests/                  → 470 Python + 76 Vitest + 13 E2E tests
├── docs/
│   ├── ARCHITECTURE.md     → System architecture and data flow
│   ├── MODULES.md          → Module responsibilities and interfaces
│   └── HEALTH.md           → Known issues and refactoring candidates
├── skills/                 → Skill definitions for specialized tasks
└── memory/                 → SQLite database
```

## Features

### 10 Tools
`fetch_url`, `web_search`, `save_memory`, `read_file`, `write_file`, `read_skill`, `get_tool_history`, `save_widget`, `get_widget_code`, `update_widget`. Auto-registered via `importlib` filesystem scan.

### Streaming with visual phases
Each interaction is shown in sequenced phases: reasoning → tools → reasoning → tools → final response. Tools are shown as pills with spinner (calling) and checkmark (ok).

### Parallel tools
The model can call multiple tools in a single iteration. They execute in parallel via `ThreadPoolExecutor`. Results arrive as they complete.

### Web dashboard
- Sidebar with sessions (rename, delete, navigate)
- History with reasoning and tools preserved after F5
- Live Debug panel: model, reasoning, tools, system prompt, stream log, UI log
- ES modules + Vite (HMR, production build)

### Episodic memory
Each tool call is logged with timestamp, input, status, and phase number. Reasoning phases are saved as JSON to reconstruct the visual sequence after refresh.

### Dynamic context
SOUL.md, MEMORY.md, AGENTS.md are auto-created on first boot. TOOLS.md is auto-generated from the tool registry. `get_tool_history` lets the model query its own tool usage.

### History compressor
When the conversation exceeds 40 messages or ~6k tokens, old messages are summarized via LLM.

### Widget system
- Inline widgets rendered in sandboxed iframes
- Official widgets: versioned, persisted in DB, toolbar with edit/history/reset
- `[Widget: id]` tag auto-renders from database

### Security
- Content-Security-Policy headers on all HTTP responses
- SSRF validation on `fetch_url` redirect chain
- Path traversal guard with `realpath` + `commonpath`
- XSS escaping in frontend (innerHTML → textContent fallback)
- Rate limiter per session (tools) and per IP (HTTP)
- Debug endpoint requires `X-Debug-Token` header or `TESTING=1`

### Architecture
- API Facade pattern: single entry point for all DB operations
- Repository Pattern with typed CRUD operations
- DI container for circular import resolution
- DatabaseEngine Protocol for future multi-DB support
- Provider injection via `LLM_PROVIDER` env var

## Startup

```bash
# CLI
python -m src.cli

# Web dashboard
python web/server.py
# → http://127.0.0.1:8000
```

### Docker

```bash
# Build and run
docker compose up --build

# Or build manually
docker build -t kairos .
docker run -p 8000:8000 -v ./memory:/app/memory kairos
```

## Tests

```bash
# Python (unit + integration)
python -m pytest tests -v

# JS (Vitest)
npx vitest run

# E2E (Playwright)
npx playwright test
```

## License

Este proyecto no tiene licencia pública definida. Todos los derechos reservados.

## Add a tool

Create a file in `src/tools/` with `DEFINITION` + `run()`. It registers automatically.

```python
DEFINITION = {
    "type": "function",
    "function": {
        "name": "my_tool",
        "description": "What it does",
        "parameters": {"type": "object", "properties": {...}}
    }
}

def run(**kwargs) -> str:
    return "result"
```

## Philosophy — "Legos"

Each piece is independent and replaceable:
- Tools → loose files in `src/tools/`
- Context → markdown files in root
- Memory → pure SQLite, no ORM
- Frontend → HTML + CSS + JS vanilla + Vite, no heavy frameworks

What doesn't work gets replaced, not patched.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — System architecture, data flow, persistence model
- [docs/MODULES.md](docs/MODULES.md) — Module responsibilities, public interfaces, dependency map
- [docs/CONTRACTS.md](docs/CONTRACTS.md) — Boundary contracts and refactor seams
- [docs/HEALTH.md](docs/HEALTH.md) — Known issues and refactoring candidates
- [ROADMAP.md](ROADMAP.md) — Completed features and next priorities
