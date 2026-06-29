# Architecture (v0.0.57)

## Philosophy: Legos

Every piece is an independent block connected by minimal interfaces. No central framework, no magic plugin loader. Dependency injection is explicit and lightweight (Python: composition root in `web/app_factory.py` that wires ~18 Lego blocks; TypeScript: composition root in `web/src_ts/app.ts` that wires widgets, panels, and streaming services). Each file can be read and understood on its own.

The system is organized in layers with clear boundaries:

```
┌──────────────────────────────────────────────────────────────────┐
│  Entry Points                                                    │
│  src/cli.py  │  src/gateway.py  │  web/server.py + routers/    │
│  Unified launcher: web + telegram + searxng                     │
└────────────┬──────────────────────────────────┬──────────────────┘
             │                                  │
             ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  API Domain Modules (src/api/)                                   │
│  Session, messages, widgets, debug, tools, history, db          │
│  Contracts: session_contract, widgets_contract, debug_contract  │
│  _resolve.py: resolve_deps(deps, factory, **kwargs)            │
└────────────┬──────────────────────────────────┬──────────────────┘
             │                                  │
             ▼                                  ▼
┌──────────────────────────────────────────────────────────────────┐
│  Core Layer (src/core/)                                         │
│  orchestrator.py  │  tool_loop.py  │  history_parser.py         │
│  history_rebuilder.py  │  history_ui.py                         │
│  services/ (6): HistoryService, LLMService,                     │
│    ToolExecutionService, TelemetryService, protocols, __init__  │
│  Contracts: orchestrator_contract, history_contract             │
│  Chat loop, streaming, tool phases, compression                │
└────────────┬──────────────────────────────────┬──────────────────┘
             │                                  │
        ┌────┴──────┐              ┌────────────┴────────────┐
        ▼            ▼              ▼                         ▼
┌────────────┐ ┌────────────┐ ┌──────────────┐  ┌──────────────┐
│   LLM      │ │   Tools    │ │   Memory     │  │   Context    │
│   Layer    │ │   Layer    │ │   Layer      │  │   Layer      │
│ src/llm/   │ │ src/tools/ │ │ src/memory/  │  │ src/context/ │
│ protocol   │ │ 23 tools   │ │ engine_state │  │ builder.py   │
│ adapters/  │ │ 12 private │ │ connection_  │  │ files.py     │
│ providers  │ │ helpers    │ │ pool.py      │  │ templates.py │
│ discovery  │ │ registry   │ │ schema.py    │  │ tools_docs   │
│ failover   │ │ runner     │ │ migration_   │  │              │
│ retry      │ │            │ │ runner.py    │  │              │
│ model_state│ │            │ │ migrations   │  │              │
│            │ │            │ │ (15 migs)    │  │              │
│            │ │            │ │ repos/ (10)  │  │              │
└─────┬──────┘ └────────────┘ └──────────────┘  └──────────────┘
      │
      ▼
┌──────────────────────────────────────────────────────────────────┐
│  Config (src/config_loader.py, paths.py, .env)                  │
│  Env vars, path resolution, API key validation                 │
└──────────────────────────────────────────────────────────────────┘
```

> **Note:** `src/config_loader.py` is the single config source of truth. Leaf layers (LLM, Tools, Memory, Context) do NOT import each other. Core serves as the orchestration bridge.

### Layer Boundaries (Non-Negotiable)

```
Entry (web/, src/cli.py) → API (src/api/) → Core (src/core/) → {LLM, Tools, Memory, Context} → Config
```

- `src/tools/` must NOT import `src/core/`
- `src/memory/` must NOT import `src/tools/`
- No web framework imports in domain layers (`src/api/`, `src/core/`, `src/tools/`, `src/llm/`, `src/memory/`)

## Data Flow (Streaming)

```
User → Form POST → web/routers/chat.py → web/services/chat_stream.py
                                             │
                           ┌─────────────────┴─────────────────┐
                           │  rebuild_history(session_id)       │
                           │    └→ history_rebuilder.py         │
                           │       └→ history_parser.py         │
                           │  save_message_record(user msg)     │
                           │  orchestrator.chat_stream()        │
                           └─────────────────┬─────────────────┘
                                             │
                           ┌─────────────────┴─────────────────┐
                           │  build_system_prompt(model)        │
                           │    └→ context/builder.py           │
                           │       └→ context/files.py          │
                           │       └→ context/templates.py      │
                           │  src.llm.client.chat_stream()      │
                           │  for chunk in stream:              │
                           │    _process_chunks()               │
                           │    if tool_calls:                   │
                           │      runner.run_parallel_tools()   │
                           │        └→ _tool_parser.py          │
                           │        └→ _rate_limiter.py         │
                           │        └→ _tool_persister.py       │
                           │      _process_tool_delta()         │
                           │    yield chunk                     │
                           └─────────────────┬─────────────────┘
                                             │
                           ┌─────────────────┴─────────────────┐
                           │  message_persister.py              │
                           │    └→ save_assistant_message()     │
                           │       └→ save_message_record()     │
                           │       └→ save_debug_info()         │
                           │  auto_rename_session()             │
                           │  yield ("content", tokens...)      │
                           │  save_message_record(phases=...)   │
                           └─────────────────┬─────────────────┘
                                             │
                      ┌──────────────────────┴──────────────────┐
                      │  NDJSON → stream-dispatcher.js          │
                      │    └→ streaming/reasoning-handler.ts    │
                      │       → <details class="reasoning">     │
                      │    └→ streaming/tool-call-renderer.ts    │
                      │       → .tc-item pills (spinner/✓/✗)    │
                      │    └→ streaming/ContentHandler.ts       │
                      │       → .msg-body token by token        │
                      │       → widget detection + init         │
                      └─────────────────────────────────────────┘
```

### Sync Path (CLI)

```
User input → src/cli.py → core.orchestrator.chat_stream()
                             └→ src.llm.client.chat(history, model, tools=TOOLS)
                             └→ tool_loop.run_tool_loop_sync()
                                   └→ _process_sync_turn() (max 5 turns)
                                   └→ save_message_record() per turn
```

## `src/` Root — Package Infrastructure (10 modules)

| File | Purpose |
|------|---------|
| `_types.py` | `MessageRecord`, `HistoryMessage`, `DebugInfo` — core type definitions |
| `background_tasks.py` | Background task runner (fire-and-forget, lifecycle-managed) |
| `chat_journal.py` | Chat journal logging (persistent conversation log) |
| `cli.py` | Console entry point — REPL loop, session management |
| `cli_commands.py` | CLI command parser (subcommands, flags, argument dispatch) |
| `compressor.py` | History compression (token-aware truncation) |
| `config_loader.py` | Single config source of truth — env vars, `.env`, path resolution |
| `constants.py` | System-wide constants (model names, limits, defaults) |
| `gateway.py` | Unified launcher — starts web + telegram + searxng |
| `gateway_log.py` | Gateway-level logging setup |
| `paths.py` | Path resolution (`CONTEXT_DIR`, `LOG_DIR`, `DB_DIR`) |
| `__init__.py` | Package marker only |

## Module Responsibilities

### `src/api/` — Domain Modules
- `__init__.py`: package marker only.
- Public functions grouped by domain: `save_message_record()` (canonical), `rebuild_history()`, `get_sessions()`, `rename_session()`, `delete_session()`, `get_session_messages()`, `filter_messages_for_ui()`, `match_tools_to_msgs()`, `save_widget_state()` / `db_save_widget()` / `db_get_widget()` / `db_get_widget_versions()` / `db_get_widget_by_version()` (all with `WidgetOpsDeps`), `save_debug_info()`, `get_debug_info()`, `get_tool_history()`.
- Sub-modules: `messages.py`, `session.py`, `widgets.py`, `debug.py`, `tools.py`, `history_parser.py`, `history_rebuilder.py`, `history_ui.py`.
- Contracts: `session_contract.py` (`SessionOpsDeps`), `widgets_contract.py` (`WidgetOpsDeps`), `debug_contract.py` (`DebugOpsDeps`).
- `_resolve.py`: `resolve_deps(deps, factory, **kwargs)` — returns `deps` if not None, otherwise calls factory. Standard dependency resolution pattern.

### `src/core/orchestrator.py` — The Brain
- `chat_stream()`: Main streaming generator. Manages full lifecycle of a conversation turn.
- `_save_debug_info()`: Saves debug snapshot with history_before, tool_calls, phases.
- `_compress_if_needed()`: Compresses history when token count exceeds threshold.
- Integrates with compressor, context builder, LLM client, tool runner, and memory.
- Contracts: `orchestrator_contract.py` (`OrchestratorDeps`, `LLMDeps`, `ToolDeps`, `StorageDeps`, `RequestStateDeps`).

### `src/core/tool_loop.py` — Tool Execution Loop
- `run_tool_loop_streaming()`: Streaming tool loop with `_ToolLoopContext` dataclass.
- `run_tool_loop_sync()`: Synchronous tool loop for CLI.
- `_process_tool_turn()`: Processes a single tool turn (streaming).
- `_process_sync_turn()`: Processes a single tool turn (sync).
- `_process_llm_stream()`: Reads LLM stream, yields content/reasoning/tool_calls.
- `_yield_stream_fallback()`: Fallback when streaming fails.

### `src/core/services/` — Service Layer (6 files)

| File | Exports | Purpose |
|------|---------|---------|
| `history_service.py` | `HistoryService` | History rebuild orchestration |
| `llm_service.py` | `LLMService` | LLM call orchestration with retry |
| `tool_execution_service.py` | `ToolExecutionService` | Tool execution lifecycle |
| `telemetry_service.py` | `TelemetryService` | Telemetry collection and persistence |
| `protocols.py` | 4 Protocols | `HistoryServiceProtocol`, `LLMServiceProtocol`, `ToolExecutionServiceProtocol`, `TelemetryServiceProtocol` |
| `__init__.py` | package marker | Marker only |

### `src/core/history_parser.py`, `src/core/history_rebuilder.py`, `src/core/history_ui.py`
- `history_parser.py`: Parse raw DB rows into messages.
- `history_rebuilder.py`: Rebuild LLM-ready history from parsed rows.
- `history_ui.py`: Filter messages for UI and match tool calls to assistant turns.
- Contract: `history_contract.py` (`HistoryRebuildDeps`).

### `src/llm/` — Model Abstraction
- `protocol.py`: `LLMProvider` runtime-checkable Protocol. Defines `chat()`, `chat_stream()`, `list_models()`.
- `adapters/openai_adapter.py`: `OpenAIAdapter` — OpenAI/OpenCode SDK wrapper. Registry-backed provider implementation.
- `api_call.py`: `_api_call()` with retry.
- `client.py`: `chat()` and `chat_stream()` with error handling, tool delta processing, debug usage tracking.
- `discovery.py`, `verifier.py`, `selector.py`, `failover.py`: model discovery, verification, selection, and failover.
- `model_state.py`: `ModelState` — thread-safe model state tracking, `_switch_model()` failover logic, `PRIORITY`/`FALLBACK_MODEL` constants.
- `retry.py`: `execute_with_retry()` — retry logic for LLM calls with exponential backoff and rate limit handling.
- `providers.py`: `_PROVIDER_REGISTRY` dict, `register_provider()` for dynamic provider registration, `_get_provider()` lazy singleton.
- `__init__.py`: Package marker only.

### `src/tools/` — Tool System (23 public + 12 private + 3 infra = 38 files)

**Public tools** (each exports `DEFINITION` dict + `run(**kwargs)`):

| Tool | Purpose |
|------|---------|
| `analyze_code` | AST-based code analysis and structure insight |
| `dependency_graph` | Build dependency graph from file imports |
| `edit_file` | Context-aware file editing (exact string replacement) |
| `execute_command` | Shell command execution (with timeout/sandbox) |
| `extract_text` | Text extraction from PDF/images/Office docs |
| `fetch_url` | HTTP URL fetching (markdown/text/html) |
| `find_dead_code` | Dead code detection across project |
| `get_tool_history` | Retrieve tool execution history |
| `get_widget_code` | Fetch saved widget code from DB |
| `git_operation` | Git operations (status, diff, log, commit) |
| `impact_analysis` | Cross-file impact analysis |
| `list_files` | File listing with glob pattern matching |
| `read_file` | Read file content with line range support |
| `read_multiple` | Batch read of multiple files |
| `read_skill` | Load skill instructions from skills/ |
| `run_code` | Python sandbox execution (restricted runtime) |
| `save_memory` | Save user memory entries |
| `save_widget` | Persist widget code to DB |
| `search_files` | Content grep search across project |
| `update_widget` | Update existing saved widget |
| `validate_all` | Multi-language syntax validation |
| `web_search` | Web search via DuckDuckGo / configurable backend |
| `write_file` | Write content to file |

**Private helpers** (12 files, no DEFINITION/run, imported by tools):

| Helper | Purpose |
|--------|---------|
| `_analyzers.py` | Language detection, AST analysis, regex patterns |
| `_arch_checker.py` | Architecture constraint validation |
| `_contract.py` | Tool contract validation |
| `_cross_analyzer.py` | Cross-file analysis helpers |
| `_path_helpers.py` | `validate_path()` — path traversal guard (realpath + commonpath) |
| `_preflight.py` | Pre-flight checks before tool execution |
| `_rate_limiter.py` | `_check_rate_limit(session_id)` — per-session rate limiting (30 calls/10s window) |
| `_tool_parser.py` | `_parse_tool_call(tc, tool_map)` — extracts name/args/error from LLM tool calls |
| `_tool_persister.py` | `_persist_tool_result()` — saves tool call logs to DB |
| `_validators.py` | Cross-language syntax validators (Python, JS, HTML, CSS, JSON, YAML) |
| `_widget_helpers.py` | `sanitize_widget_id()`, `validate_widget_args()` |
| `loader.py` | (Deprecated) Legacy filesystem scanner — kept for backward compat |

**Infrastructure** (3 files):
- `__init__.py`: Auto-loader via `importlib`. Exports `TOOLS` (schema for LLM), `TOOL_MAP` (execution), `TOOL_DEFINITIONS` (metadata).
- `registry.py`: Tool registry — `discover_tools()`, `get_tool()`, `list_tools()`.
- `runner.py`: `run_parallel_tools()` — executes tool calls via `ThreadPoolExecutor`, yields streaming events.

### `src/memory/` — Persistence Layer
- `db_path.py`: DB path resolution from config/env.
- `engine_state.py`: `DatabaseEngine` Protocol for swappable backends. `get_engine()` / `set_engine()` for engine injection.
- `lifecycle.py`: Initialized-path registry so connection pooling can bootstrap each DB path once.
- `connection_pool.py`: Pooled SQLite connections (thread-local, WAL mode, busy timeout).
- `schema.py`: `init_db()` and per-path schema initialization / version bootstrap.
- `migration_runner.py`: Pending migration execution and `schema_version` updates.
- `sqlite_engine.py`: `SQLiteEngine` — default SQLite implementation of `DatabaseEngine` with WAL mode.
- `migrations.py`: 15 migration functions from `_migration_001_initial_schema` to `_migration_015_chat_journal`. Idempotent via `IF NOT EXISTS` and `try/except OperationalError`.

**Repos** (10 files in `src/memory/repos/`):

| File | Exports |
|------|---------|
| `base.py` | `_BaseRepository` — `_get_conn()`, `_transaction()` context manager |
| `message_repository.py` | `MessageRepository` + `MessageRecord` dataclass |
| `session_repository.py` | `SessionRepository` — create, rename, delete, list |
| `tool_call_repository.py` | `ToolCallRepository` — log, get_history, delete |
| `widget_state_repository.py` | `WidgetStateRepository` — save/load widget states |
| `debug_repository.py` | `DebugRepository` — save/get debug snapshots |
| `saved_widget_repository.py` | `SavedWidgetRepository` — save, get, versions |
| `memory_index_repository.py` | `MemoryIndexRepository` — upsert/lookup memory index |
| `protocols.py` | 7 repo protocols: `MessageRepository`, `SessionRepository`, `ToolCallRepository`, `WidgetStateRepository`, `DebugRepository`, `SavedWidgetRepository`, `MemoryIndexRepository` |
| `__init__.py` | `Repositories` dataclass + `get_repos(conn)` factory |

### `src/context/` — Context Assembly (Package)
- `__init__.py`: Re-exports `load_context`, `build_system_prompt`, `_build_tools_md`, `_ensure_file`, `_read_file`.
- `builder.py`: `build_system_prompt(model)` — assembles system message from SOUL.md + AGENTS.md + MEMORY.md + dynamic meta block. `load_context()` — loads markdown files, auto-creates them if missing.
- `files.py`: `_ensure_file(path, template)` — creates file from template if missing. `_read_file(path)` — reads file content.
- `templates.py`: `TEMPLATES` dict with default content for SOUL.md, MEMORY.md, AGENTS.md.
- `tools_docs.py`: `_build_tools_md()` — generates TOOLS.md from `TOOL_DEFINITIONS` dynamically.

### `src/skills/` — Skill System
- `registry.py`: `SkillRegistry` — `discover(path)`, `discover_tools()`, `generate_index_md()`.
- Skills are auto-discovered from `skills/` directory at startup.
- `generate_index_md()` writes `skills/INDEX.md` with available skills and metadata.

### `channels/` — External Integrations
- `__init__.py`: Auto-discover channels via `importlib`.
- `channels/telegram/`: Telegram bot integration.
  - `bot.py`: Telegram bot instance (python-telegram-bot based).
  - `adapter.py`: Adapter converts Telegram messages to internal format and routes responses.
  - `handlers.py`: Message/command handlers for Telegram.
  - `config.py`: Telegram-specific config (token, allowed users, rate limits).
  - `__main__.py`: Standalone Telegram bot entry point.

### `src/gateway.py` — Unified Launcher
- `launch()`: Starts three services concurrently:
  1. **Web**: FastAPI server (`web/server.py`)
  2. **Telegram**: Telegram bot (`channels/telegram/`)
  3. **SearXNG**: Local search engine instance (if configured)
- Uses `asyncio.gather()` for concurrent startup.
- Graceful shutdown via signal handlers.

### `web/` — Web Dashboard

**Server & Middleware:**
- `server.py`: FastAPI app, static files, exception handlers (unified `{"detail": ...}` JSON format), rate limiter middleware, CSP middleware, no-cache middleware.
- `logging_handler.py`: `BackendLogHandler` (ring buffer on `kairos.*` logger), `get_backend_logs()`.

**Routers:**
- `chat.py`: POST streaming endpoint with `ChatPayload` Pydantic model. NDJSON generation, error classification, debug persistence.
- `pages.py`: Chat page, sidebar, session messages (HTML rendering with phases and widgets). `get_available_model_ids()` helper.
- `sessions.py`: Rename and delete endpoints.
- `widgets.py`: Widget API with `WidgetStatePayload` and `SaveWidgetPayload` Pydantic models.
- `debug.py`: Debug info and backend log buffering. `_local_only` guard.
- `health.py`: `GET /health` — DB status, LLM provider status, uptime, system info.
- `asr.py`: Audio/ASR endpoints, WebSocket transport for live chunk transcription.
- `logs.py`: Log query endpoints.

**Services:**
- `chat_stream.py`: `build_stream_generator()` — returns NDJSON generator closure, token accumulation, background auto-rename.
- `chat_stream_contract.py`: `StreamGeneratorDeps` — bundles stream hooks and retry/save dependencies.
- `stream_state.py`: `StreamState` — accumulates partial content/reasoning and persistence timing.
- `message_persister.py`: `save_assistant_message()` — persists assistant message and debug info to DB.
- `message_persister_contract.py`: `MessagePersisterDeps` — optional dependency bundle.
- `message_renderer.py`: `render_session_messages(session_id)` — full HTML message list with widgets, tool matching, XSS escaping.
- `message_renderer_contract.py`: `MessageRenderDeps` — optional dependency bundle.
- `stream_error_classifier.py`: `classify_error(error_msg)` — classifies error into type + user-friendly message.
- `stream_retry_handler.py`: Coordinates retry logic (3 attempts, backoff 2s×attempt).
- `loop_detector.py`: Detects infinite tool-call loops and aborts.
- `file_logger.py`: Persistent file-based logging.
- `asr_service.py`: Audio/ASR processing service.
- `stream_contract.py`: `build_stream_event()` — NDJSON event builder.
- `widget_contract.py`: `normalize_inline_widget_code()` — widget code normalization.
- `ui_utils.py`: HTML rendering helpers — `render_msg_with_phases()`.

**Frontend — 42 JS/TS modules, 9 CSS files:**
- `streaming/StreamDispatcher.ts`: `KairosStream` — event emitter with `on()` / `emit()`. Central dispatcher for reasoning, content, tool_call, error events.
- `streaming/reasoning-handler.ts`: Handles `reasoning` events — creates `<details class="reasoning">` elements, accumulates thinking text.
- `streaming/ContentHandler.ts`: Handles `content` events — manages per-phase body divs, detects inline widgets, renders markdown, initializes widgets.
- `streaming/tool-call-renderer.ts`: Handles `tool_call` events — creates `.tool-calls` divs with `.tc-item` pills.
- `streaming/StreamOrchestrator.ts`: Main stream rendering orchestrator. Wires dispatcher to handlers, manages phase transitions.
- `core/ChatForm.ts`: Chat form submission and input handling with keyboard shortcuts.
- `rendering/DomRenderer.ts`: `KairosMarkdown.parse()` — markdown to HTML conversion.
- `api-client.js`: Unified frontend API client for all endpoints.
- `skills-ui.ts`: TypeScript module — skills UI panel and management.
- `message-renderer.js`: Client-side message rendering.
- `core/DebugManager.ts`, `core/RateLimitCooldown.ts`, `core/SessionList.ts`, `sidebar-refresh.js`: UI components.
- `file-attachment.js`, `session-context.js`, `stream-completion.js`: State/behavior modules.
- `asr/` (7 modules): `contract.js`, `transcript-utils.js`, `audio-capture.js`, `pcm-utils.js`, `pcm-worklet.js`, `transcription-transport.js`, `vad.js` — microphone capture, VAD segmentation, live ASR.
- `asr-mic.js`: ES module for microphone + VAD + transcript merging.
- `widgets/` (13 modules): `index.js`, `core.js`, `contract.js`, `iframe.js`, `iframe-builder.js`, `messaging.js`, `state-manager.js`, `widget-detector.js`, `toolbar-core.js`, `toolbar-editor.js`, `toolbar-history.js`, `ui-helpers.js`, `canvas-workspace.ts` — sandboxed iframe widgets with postMessage protocol.

## Wire Format

```
NDJSON (application/x-ndjson)

{"t":"reasoning","d":"thinking..."}          → new reasoning phase
{"t":"tool_call","d":"{\"id\":\"c1\",...}"}   → calling / result
{"t":"content","d":" token"}                  → final response token
{"t":"error","d":{"type":"...","message":"..."}} → error
{"t":"heartbeat","d":""}                      → keepalive (every 10s)
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
- `memory_index`: key(PK), value, created_at, updated_at
- `gateway_logs`: id(PK), service, level, message, created_at
- `chat_journal`: id(PK), session_id, role, content, created_at

All `session_id` columns defined with `REFERENCES sessions(session_id)` (enforced when `PRAGMA foreign_keys=ON`).

### Indexes
- `idx_messages_session_id` on `messages(session_id)`
- `idx_tool_calls_session_id` on `tool_calls(session_id)`
- `idx_saved_widgets_session_id` on `saved_widgets(session_id)`
- `idx_widget_versions_session_id` on `widget_versions(session_id)`
- `idx_tool_calls_session_id_turn` on `tool_calls(session_id, turn)` — composite index
- `idx_gateway_logs_created` on `gateway_logs(created_at)`

## Widget System

Widgets are self-contained HTML/CSS/JS snippets rendered in sandboxed iframes.
- Inline widgets: ` ```html-widget [key]\n...\n``` ` → rendered immediately
- Official widgets: `[Widget: key]` → fetches code from DB and renders
- State persistence: via `window.__KAIROS_WIDGET_BRIDGE__.saveState()` → POST to backend → `widget_states` table
- Toolbar: version badge, edit button, history/rollback, reset state
- Host↔iframe communication: `postMessage` protocol (sandboxed, origin-verified)

## Contracts

Dependency contracts follow two patterns:

### Protocol Pattern (Runtime-checkable Protocols)
12 Protocols across the system:

| Protocol | File | Methods |
|----------|------|---------|
| `LLMProvider` | `src/llm/protocol.py` | `chat()`, `chat_stream()`, `list_models()` |
| `DatabaseEngine` | `src/memory/engine_state.py` | Engine lifecycle methods |
| `MessageRepository` | `src/memory/repos/protocols.py` | Message CRUD |
| `SessionRepository` | `src/memory/repos/protocols.py` | Session CRUD |
| `ToolCallRepository` | `src/memory/repos/protocols.py` | Tool call log |
| `WidgetStateRepository` | `src/memory/repos/protocols.py` | Widget state persistence |
| `DebugRepository` | `src/memory/repos/protocols.py` | Debug info CRUD |
| `SavedWidgetRepository` | `src/memory/repos/protocols.py` | Saved widget CRUD |
| `MemoryIndexRepository` | `src/memory/repos/protocols.py` | Memory index CRUD |
| `HistoryServiceProtocol` | `src/core/services/protocols.py` | History rebuild |
| `LLMServiceProtocol` | `src/core/services/protocols.py` | LLM orchestration |
| `ToolExecutionServiceProtocol` | `src/core/services/protocols.py` | Tool execution |
| `TelemetryServiceProtocol` | `src/core/services/protocols.py` | Telemetry collection |
| `StreamGeneratorProtocol` | `web/services/protocols.py` | Stream generation |
| `MessagePersisterProtocol` | `web/services/protocols.py` | Message persistence |
| `MessageRendererProtocol` | `web/services/protocols.py` | HTML rendering |

### Deps Dataclass Pattern (Namedtuples/dataclasses for injection)
- `src/api/session_contract.py`: `SessionOpsDeps`
- `src/api/widgets_contract.py`: `WidgetOpsDeps`
- `src/api/debug_contract.py`: `DebugOpsDeps`
- `src/core/orchestrator_contract.py`: `OrchestratorDeps`, `LLMDeps`, `ToolDeps`, `StorageDeps`, `RequestStateDeps`
- `src/core/history_contract.py`: `HistoryRebuildDeps`
- `web/services/chat_stream_contract.py`: `StreamGeneratorDeps`
- `web/services/message_persister_contract.py`: `MessagePersisterDeps`
- `web/services/message_renderer_contract.py`: `MessageRenderDeps`
- `web/services/widget_contract.py`: `normalize_inline_widget_code()`
- `web/services/stream_contract.py`: `build_stream_event()`

### Resolve Pattern

```python
def resolve_deps(deps, factory, **kwargs):
    return deps if deps is not None else factory(**kwargs)
```

Standardized in `src/api/_resolve.py`. Used across API, Core, and Web layers to allow optional dep injection with automatic fallback to configured defaults.

## Channels

Channels extend K-Chat to external platforms beyond the web UI. Each channel is an independent adapter.

```
                     ┌──────────────┐
                     │  src/gateway │
                     │  .py         │
                     └──────┬───────┘
                            │
          ┌─────────────────┼─────────────────┐
          ▼                 ▼                  ▼
   ┌───────────┐    ┌──────────────┐    ┌──────────┐
   │   Web     │    │   Telegram   │    │ SearXNG  │
   │  server   │    │    bot       │    │ (optional)│
   └───────────┘    └──────────────┘    └──────────┘
```

### Telegram Channel
- `channels/telegram/bot.py`: `Application` from python-telegram-bot.
- `channels/telegram/adapter.py`: Converts Telegram `Message` → internal `HistoryMessage`, sends responses back.
- `channels/telegram/handlers.py`: `/start`, `/help`, `/new`, text message handlers.
- `channels/telegram/config.py`: Bot token, allowed user IDs, rate limits.
- `__main__.py`: Standalone entry point for development.

**Channel architecture:**
```
Telegram Message → handler → adapter.to_internal()
    → core.orchestrator.chat_stream()
    → adapter.to_telegram() → bot.send_message()
```

## Skills

Skills are reusable, specialized instruction sets that guide tool behavior. They live in `skills/` as markdown files.

### Directory Layout
```
skills/
├── INDEX.md              # Auto-generated by SkillRegistry
├── db-query/
│   ├── tool.py           # Tool implementation (DEFINITION + run)
│   └── db-query.md       # Skill instructions
├── document-processing/
│   └── document-processing.md
└── html-widgets/
    └── html-widgets.md
```

### SkillRegistry (`src/skills/registry.py`)
- `discover(path)`: Scans `skills/` for subdirectories with `.md` files.
- `discover_tools()`: Finds `tool.py` files within skill directories, loads them as tools.
- `generate_index_md()`: Writes `skills/INDEX.md` with name, description, and available tools for each skill.
- Skills are loaded via `read_skill` tool at runtime.
- The web router reads the registry from `app.state.skill_registry`; if that state is missing in a real request, it fails fast instead of constructing ad hoc state.

## Gateway

`src/gateway.py` is the unified launcher that starts all services:

```
gateway.launch()
├── start_web()        # uvicorn → web/server.py
├── start_telegram()   # PTB Application → channels/telegram/
└── start_searxng()    # subprocess → searxng (if configured)
    └── all via asyncio.gather()
```

- Graceful shutdown: catches `SIGINT`/`SIGTERM`, stops all services.
- `gateway_log.py`: Structured logging with service tags.
- `gateway_logs` table: persists gateway-level events to DB.
- Each service can also run standalone: `python -m src.gateway` for all, or individual entry points.

## Key Design Decisions

| Decision | Chosen | Alternative |
|----------|--------|-------------|
| Runtime | Python pure | TypeScript |
| LLM client | OpenAI SDK | httpx direct |
| Provider model | Protocol + registry | Hardcoded switch |
| DB engine | `DatabaseEngine` Protocol + `SQLiteEngine` | Hardcoded SQLite calls |
| Memory | SQLite native + Markdown | sqlite-vec / external |
| Stream | Sync generator | Async complex |
| Config | `.env` + Markdown | YAML large |
| Tools | `importlib` auto-registry | Manual registration |
| Tool count | 23 public + 12 private + 1 skill | Smaller set |
| Tool helpers | Split: rate_limiter, parser, persister, validators, helpers | Monolithic runner |
| DB repos | `_BaseRepository` + 7 subclasses + protocols | One god class |
| DB transactions | `_transaction()` context manager with rollback | Bare commit() |
| Migrations | 15 idempotent functions | 9 earlier |
| History | Split: parser, rebuilder, ui | Legacy history.py |
| Context | Package with builder, files, templates, tools_docs | Single context.py |
| Services | Core services/ (6 files) + web services/ | Ad-hoc |
| Contracts | Protocols (12) + Deps dataclasses (9) + _resolve pattern | No contracts |
| Channels | Telegram adapter + ready for more | Heavy gateway from day one |
| Skills | `skills/` + `SkillRegistry` | Hardcoded instructions |
| Gateway | Unified launcher (web + telegram + searxng) | Separate processes |
| Frontend | 42 Vanilla JS/TS modules (no build) | React / Vue |
| Stream events | `KairosStream` event emitter → handler modules | Inline JS |
| Rate limiting | Tool-level (30/10s per session) + HTTP (60/min per IP) + retry (3x, 2s backoff) | Single layer |
| Serialization | NDJSON | SSE |
| Error format | Unified `{"detail": "..."}` JSON | Mixed HTML/JSON |
| Validation | Pydantic models for web routers | Raw `dict[str, Any]` |
| CSS | Custom properties on `:root` (9 CSS files) | Hardcoded colors |
| Security | CSP headers + SSRF validation + path traversal guard + iframe sandbox | No defense |
| ASR | 7 modules + WebSocket transport | No speech support |
