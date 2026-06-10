# Architecture

## Philosophy: Legos

Every piece is an independent block connected by minimal interfaces. No central framework, no magic plugin loader, no DI container. Each file can be read and understood on its own.

The system is organized in layers with clear boundaries:

```
┌─────────────────────────────────────────────────────────────┐
│  Entry Points                                               │
│  CLI (src/cli.py)   │   Web (web/server.py + routers/)    │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│  API Facade (src/api.py)                                   │
│  Single entry point for all web routers.                   │
│  Lazy repository singletons, all DB ops through this.      │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Core Layer (src/core/)                                     │
│  orchestrator.py  │  tool_loop.py  │  history.py           │
│  chat_sync.py     │  _deps.py                              │
│  Chat loop, streaming, tool phases, compression            │
└──────────┬──────────────────────────────┬───────────────────┘
           │                              │
      ┌─────┴──────┐              ┌────────┴────────┐
      ▼            ▼              ▼                 ▼
┌────────┐  ┌──────────┐  ┌──────────────┐  ┌────────────┐
│  LLM   │  │  Tools   │  │   Memory     │  │  Context   │
│  Layer │  │  Layer   │  │   Layer      │  │  Layer     │
│src/llm/│  │src/tools/│  │ src/memory/  │  │src/context │
│protocol│  │loader.py │  │ database.py  │  │_build_tools│
│provider│  │runner.py │  │repositorie s │  │_md() lazy  │
│models  │  │10 tools  │  │migrations.py │  │import tool │
│client  │  │          │  │              │  │definitions │
│manager │  │          │  │              │  │            │
└───┬────┘  └──────────┘  └──────────────┘  └────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Config (config.py, paths.py, .env)                         │
│  Env vars, path resolution, API key validation              │
└─────────────────────────────────────────────────────────────┘
```

## Data Flow (Streaming)

```
User → Form POST → web/routers/chat.py → web/services/chat_stream.py
                                            │
                          ┌─────────────────┴─────────────────┐
                          │  rebuild_history(session_id)      │
                          │  save_message(user message)       │
                          │  orchestrator.chat_stream()       │
                          └─────────────────┬─────────────────┘
                                            │
                          ┌─────────────────┴─────────────────┐
                          │  build_system_prompt(model)       │
                          │  _deps.llm_stream()                │
                          │  for chunk in stream:              │
                          │    _process_chunks()               │
                          │    if tool_calls:                  │
                          │      runner.run_parallel_tools()   │
                          │      _process_tool_delta()         │
                          │    yield chunk                     │
                          └─────────────────┬─────────────────┘
                                            │
                          ┌─────────────────┴─────────────────┐
                          │  save_assistant_message()          │
                          │  auto_rename_session()             │
                          │  yield ("content", tokens...)      │
                          │  save_message(phases=JSON)         │
                          └─────────────────┬─────────────────┘
                                            │
                     ┌──────────────────────┴──────────────────┐
                     │  NDJSON → browser JS reads stream       │
                     │  reasoning → <details> per phase        │
                     │  tool_call → pills with spinner/✓       │
                     │  content → msg-body token by token      │
                     └─────────────────────────────────────────┘
```

### Sync Path (CLI)

```
User input → src/cli.py → core.chat_sync.chat()
                            └→ _deps.llm_chat(history, model, tools=TOOLS)
                            └→ tool_loop.run_tool_loop_sync()
                                  └→ _process_sync_turn() (max 5 turns)
                                  └→ save_message() per turn
```

## Module Responsibilities

### `src/api.py` — Public Facade
- Single entry point for web routers. All DB ops through this.
- 19+ public functions: `get_repos()`, `save_message()`, `rebuild_history()`, `get_sessions()`, `rename_session()`, `delete_session()`, `get_session_messages()`, `filter_messages_for_ui()`, `match_tools_to_msgs()`, `save_widget_state()`, `db_save_widget()`, `db_get_widget()`, `db_get_widget_versions()`, `db_get_widget_by_version()`, `save_debug_info()`, `get_debug_info()`, `get_tool_history()`, `chat_stream()`.
- Lazy repository singletons via `_get_message_repo()`, `_get_session_repo()`, etc.

### `src/core/orchestrator.py` — The Brain
- `chat_stream()`: Main streaming generator. Manages the full lifecycle of a conversation turn (84 lines).
- `_save_debug_info()`: Saves debug snapshot with history_before, tool_calls, phases.
- `_compress_if_needed()`: Compresses history when token count exceeds threshold.
- Integrates with compressor, context builder, LLM client, tool runner, and memory.

### `src/core/tool_loop.py` — Tool Execution Loop
- `run_tool_loop_streaming()`: Streaming tool loop with `_ToolLoopContext` dataclass (11 params consolidated).
- `run_tool_loop_sync()`: Synchronous tool loop for CLI.
- `_process_tool_turn()`: Processes a single tool turn (streaming).
- `_process_sync_turn()`: Processes a single tool turn (sync).
- `_process_llm_stream()`: Reads LLM stream, yields content/reasoning/tool_calls.
- `_yield_stream_fallback()`: Fallback when streaming fails.

### `src/core/history.py` — History Reconstruction
- `rebuild_history()`: Reconstructs a conversation from the DB for the LLM, sanitizing tool_calls and tool responses.
- `filter_messages_for_ui()`: Filters DB rows for UI display (removes intermediate assistant/tool messages, keeps the final one per turn).
- `match_tools_to_msgs()`: Associates tool calls chronologically with assistant messages for rendering.

### `src/core/chat_sync.py` — CLI Chat
- `chat()`: Synchronous wrapper. Calls `llm_chat(history, model, tools=TOOLS)`, returns response content.

### `src/core/_deps.py` — Dependency Wiring
- Module-level `functools.partial` wrappers: `llm_chat`, `llm_stream`, `build_system_prompt`, `TOOL_MAP`.
- Centralizes imports to avoid circular dependencies.

### `src/llm/` — Model Abstraction
- `protocol.py`: `LLMProvider` runtime-checkable Protocol. Defines `chat()`, `chat_stream()`, `list_models()`.
- `openai_provider.py`: `OpenAIProvider` — OpenAI/OpenCode SDK wrapper. Lazy `_get_provider()` singleton.
- `models.py`: Model registry, `PRIORITY`/`FALLBACK_MODEL` constants, `_api_call()` with retry, `_switch_model()`, `register_provider()`.
- `client.py`: `chat()` and `chat_stream()` with error handling, tool delta processing, debug usage tracking.
- `manager.py`: Model discovery, verification (`verify_model`), priority selection, free/paid filtering.
- `__init__.py`: Module facade exposing unified interface.

### `src/tools/` — Tool System
- `__init__.py`: Auto-loader via `importlib`. Exports `TOOLS` (schema for LLM), `TOOL_MAP` (execution), `TOOL_DEFINITIONS` (metadata).
- `loader.py`: Filesystem scan + dynamic imports at module load. Populates `TOOL_MAP` and `TOOL_DEFINITIONS`.
- `runner.py`: `run_parallel_tools()` — executes tool calls via `ThreadPoolExecutor`, yields streaming events. Per-session rate limiter (`_session_rate` with LRU eviction, `_rate_lock`).
- `_path_helpers.py`: `validate_path()` — path traversal guard using `os.path.realpath` + `commonpath`.
- `_widget_helpers.py`: `sanitize_widget_id()`, `validate_widget_args()`.
- Individual tools (10): Each exports `DEFINITION` (dict) + `run(**kwargs)`. New tool = new file.

### `src/memory/` — Persistence Layer
- `database.py`: SQLite connection factory (WAL mode, busy timeout). `PooledConnection` wrapper (no-op close). `init_db()` with `PRAGMA foreign_keys = ON`.
- `repositories.py`: 6 repository classes (`MessageRepository`, `SessionRepository`, `ToolCallRepository`, `WidgetStateRepository`, `DebugRepository`, `SavedWidgetRepository`) inheriting from `_BaseRepository`. All methods wrapped in `_transaction()` context manager with rollback on exception.
- `migrations.py`: 9 migration functions from `_migration_001_initial_schema` to `_migration_009_add_indexes`. Idempotent via `IF NOT EXISTS` and `try/except OperationalError`.

### `src/context.py` — Context Assembly
- `build_system_prompt()`: Assembles the system message from SOUL.md + AGENTS.md + MEMORY.md + dynamic meta block.
- `load_context()`: Loads markdown files, auto-creates them if missing.
- `_build_tools_md()`: Generates TOOLS.md from `TOOL_DEFINITIONS` dynamically (lazy import of `src.tools`).

### `web/` — Web Dashboard
- `server.py`: FastAPI app, static files, exception handlers (unified `{"detail": ...}` JSON format), rate limiter middleware, CSP middleware, no-cache middleware.
- `logging.py`: `BackendLogHandler` (ring buffer on `kairos.*` logger), `get_backend_logs()`.
- `routers/chat.py`: POST streaming endpoint with `ChatPayload` Pydantic model. Handles NDJSON generation, error classification, debug persistence.
- `routers/pages.py`: Routes for chat page, sidebar, session messages (HTML rendering with phases and widgets). `get_available_model_ids()` helper.
- `routers/sessions.py`: Rename and delete endpoints.
- `routers/widgets.py`: Widget API with `WidgetStatePayload` and `SaveWidgetPayload` Pydantic models.
- `routers/debug.py`: Debug info and backend log buffering. `_local_only` guard (respects `TESTING` env var).
- `services/chat_stream.py`: NDJSON stream generator, `_classify_error()`, token accumulation, background auto-rename.
- `services/message_renderer.py`: `render_session_messages()` — full HTML message list with widgets, tool matching, XSS escaping.
- `ui_utils.py`: HTML rendering of individual messages with reasoning, phases, and tool pills. `render_msg_with_phases()`.

## Wire Format

```
NDJSON (application/x-ndjson)

{"t":"reasoning","d":"thinking..."}      → new reasoning phase
{"t":"tool_call","d":"{\"id\":\"c1\",...}"} → calling / result
{"t":"content","d":" token"}             → final response token
{"t":"error","d":{"type":"...","message":"..."}} → error
```

## Context Stack (System Prompt)

```
[System Info]
- Active model: <model>
- System time: <timestamp>

# SOUL.md     → identity, personality, tone
# MEMORY.md   → user data, checkpoints, bugs, visions
# AGENTS.md   → behavior rules, tool system, verification, temporal awareness
```

`TOOLS.md` is auto-generated on startup but NOT injected into the system prompt (the LLM receives the schema via the API `tools=` parameter).

## Persistence Model

### SQLite Schema
- `messages`: id(PK), session_id, role, content, model, reasoning, phases(JSON), tool_calls(JSON), tool_call_id, prompt_tokens, completion_tokens, total_tokens, created_at
- `tool_calls`: id(PK), session_id, tool_name, input, status, turn, created_at
- `sessions`: session_id(PK), name, created_at
- `widget_states`: session_id, widget_id, state, updated_at (PK: session_id+widget_id)
- `saved_widgets`: widget_id(PK), code, version, description, created_at, updated_at, session_id
- `widget_versions`: widget_id, version(PK), code, description, created_at, session_id
- `debug_info`: session_id(PK), model, reasoning, system_prompt, tool_calls, history_before, updated_at

All `session_id` columns defined with `REFERENCES sessions(session_id)` (enforced when `PRAGMA foreign_keys=ON`).

### Indexes
- `idx_messages_session_id` on `messages(session_id)`
- `idx_tool_calls_session_id` on `tool_calls(session_id)`
- `idx_saved_widgets_session_id` on `saved_widgets(session_id)`
- `idx_widget_versions_session_id` on `widget_versions(session_id)`

## Widget System

Widgets are self-contained HTML/CSS/JS snippets rendered in sandboxed iframes.
- Inline widgets: ` ```html-widget [key]\n...\n``` ` → rendered immediately
- Official widgets: `[Widget: key]` → fetches code from DB and renders
- State persistence: via `window.saveState()` → POST to backend → `widget_states` table
- Toolbar: version badge, edit button, history/rollback, reset state

## Key Design Decisions

| Decision | Chosen | Alternative |
|----------|--------|-------------|
| Runtime | Python pure | TypeScript |
| LLM client | OpenAI SDK | httpx direct |
| Provider model | Protocol + registry | Hardcoded switch |
| Memory | SQLite native + Markdown | sqlite-vec / external |
| Stream | Sync generator | Async complex |
| Config | `.env` + Markdown | YAML large |
| Tools | `importlib` auto-registry | Manual registration |
| DB repos | `_BaseRepository` + 6 subclasses | One god class |
| DB transactions | `_transaction()` context manager with rollback | Bare commit() |
| Rate limiting | Tool-level (30/10s per session) + HTTP (60/min per IP) | Single layer |
| Frontend | Vanilla JS (no build) | React / Vue |
| Serialization | NDJSON | SSE |
| Error format | Unified `{"detail": "..."}` JSON | Mixed HTML/JSON |
| Validation | Pydantic models for web routers | Raw `dict[str, Any]` |
| CSS | Custom properties on `:root` | Hardcoded colors |
| Security | CSP headers + SSRF validation + path traversal guard | No defense |
| Growth | Channels as adapters | Heavy gateway from day one |
