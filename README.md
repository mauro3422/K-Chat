# Kairos (K-Chat)

> **v0.0.53** — Personal minimalist agent with episodic memory, parallel tools, and web dashboard.
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
├── config.py               → Compat shim (re-exports from src/config_loader.py)
├── SOUL.md / MEMORY.md     → Personality and user data (auto-created)
├── AGENTS.md / TOOLS.md    → Agent rules and tool guide (auto-generated)
├── src/
│   ├── api/                → Domain modules for all DB operations
│   │   ├── __init__.py     → Package marker (empty)
│   │   ├── messages.py     → Message CRUD
│   │   ├── session.py      → Session management
│   │   ├── widgets.py      → Widget persistence
│   │   ├── debug.py        → Debug info
│   │   ├── tools.py        → Tool history
│   │   ├── history.py      → History reconstruction and UI filtering
│   │   ├── connection.py   → Re-exports get_conn from src.memory.connection
│   │   └── models.py       → Facade re-exporting from src.llm.policy and model_state
│   ├── core/
│   │   ├── orchestrator.py → Chat loop, streaming, tool phases, compression
│   │   ├── tool_loop.py    → Sync + streaming tool execution loops
│   │   ├── chat_sync.py    → Non-streaming chat helper
│   │   └── history.py      → History reconstruction and UI filtering
│   ├── llm/
│   │   ├── protocol.py     → LLMProvider protocol definition
│   │   ├── adapters/       → OpenAI-compatible provider adapters
│   │   ├── providers.py    → Provider registry
│   │   ├── model_state.py  → Thread-safe ModelState class (failed/verified/cached)
│   │   ├── retry.py        → execute_with_retry() with exponential backoff
│   │   ├── client.py       → chat() and chat_stream()
│   │   └── discovery/selection/failover modules
│   ├── memory/
│   │   ├── connection.py   → SQLite connection management
│   │   ├── schema.py       → Schema init + migrations bootstrap
│   │   ├── migrations.py   → Schema migration functions
│   │   └── repos/          → CRUD repositories (messages, sessions, tools, widgets, debug)
│   ├── tools/
│   │   ├── __init__.py     → Module exports
│   │   ├── loader.py       → Auto-loader (TOOL_MAP, TOOL_DEFINITIONS)
│   │   ├── runner.py       → Parallel tool execution
│   │   ├── rules/          → Auto-generated tool rule docs (preserves manual edits below ---)
│   │   └── 16 tools        → Individual tools
│   ├── constants.py        → Shared policy constants (MAX_TOOL_TURNS, LLM_MAX_RETRIES)
│   ├── context/
│   │   ├── builder.py      → System prompt builder
│   │   ├── files.py        → Markdown file loader/creator
│   │   ├── templates.py    → Default templates for SOUL/MEMORY/AGENTS
│   │   ├── tools_docs.py   → TOOLS.md auto-generator (lazy)
│   │   └── runtime.py      → Runtime context injection
│   ├── compressor.py       → History compression via LLM
│   ├── background_tasks.py → Auto-rename sessions
│   ├── cli.py              → CLI entry point
│   ├── handler_cli.py      → CLI commands (/model, /clear, /help)
│   └── paths.py            → Path resolution utilities
├── web/
│   ├── server.py           → FastAPI app
│   ├── logging_handler.py  → Backend log handler + ring buffer
│   ├── ui_utils.py         → HTML message renderer
│   ├── services/
│   │   ├── chat_stream.py  → Stream generator for web endpoint
│   │   ├── message_persister.py → Persists assistant messages
│   │   ├── message_renderer.py → Session message HTML renderer
│   │   ├── stream_error_classifier.py → Classify errors (rate_limit, timeout, etc.)
│   │   ├── stream_contract.py → NDJSON event contract
│   │   ├── loop_detector.py → Detects infinite tool-call loops
│   │   ├── file_logger.py  → Persistent file logging
│   │   ├── stream_retry_handler.py → Stream retry coordination
│   │   └── asr_service.py  → Audio/ASR service
│   ├── routers/
│   │   ├── chat.py         → Streaming POST endpoint
│   │   ├── pages.py        → HTML pages, sidebar, messages
│   │   ├── sessions.py     → Rename, delete
│   │   ├── widgets.py      → Widget API
│   │   ├── debug.py        → Debug info, backend logs
│   │   ├── health.py       → GET /health endpoint
│   │   ├── asr.py          → Audio/ASR endpoints
│   │   └── logs.py         → Log query endpoints
│   ├── templates/          → Jinja2 templates
│   └── static/             → CSS, JS modules (chat, session, debug, widgets)
├── tests/                  → 664 Python + 22 E2E tests (Playwright)
├── docs/
│   ├── ARCHITECTURE.md     → System architecture and data flow
│   ├── MODULES.md          → Module responsibilities and interfaces
│   └── HEALTH.md           → Known issues and refactoring candidates
├── skills/                 → Skill definitions for specialized tasks
└── memory/                 → SQLite database
```

> **Note:** Some docs may lag behind the current version. When in doubt, prefer [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and [docs/MODULES.md](docs/MODULES.md).

## Features

### 16 Tools
- `src/tools/rules/`: Auto-generated markdown docs per tool, preserving manual usage notes below `---` separators.

`fetch_url`, `web_search`, `save_memory`, `read_file`, `write_file`, `read_skill`, `get_tool_history`, `save_widget`, `get_widget_code`, `update_widget`, `list_files`, `execute_command`, `search_files`, `edit_file`, `analyze_code`, `git_operation`. Auto-registered via `importlib` filesystem scan.

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

# Optional: set KAIROS_WEB_BASE_URL to force a single canonical web link across machines.
# Otherwise the app uses the URL you used to enter the server.
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
