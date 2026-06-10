# Module Guide

This document maps every module in the system with its single responsibility, its public interface, and what it depends on.

## Layer Map

```
entry/
  cli.py              → CLI entry point (argparse, REPL loop)
  web/server.py       → FastAPI entry point (static files, middleware, exception handlers)

api/
  api.py              → Public facade: 19+ functions, lazy repos, single entry for web routers

core/
  orchestrator.py     → Chat loop, streaming, compression, debug snapshots
  tool_loop.py        → Tool call orchestration (streaming + sync), ToolLoopContext
  chat_sync.py        → Synchronous chat wrapper (CLI path)
  history.py          → History reconstruction + UI filtering
  _deps.py            → Dependency wiring (partials, avoids circular imports)

llm/
  protocol.py         → LLMProvider Protocol (runtime-checkable)
  openai_provider.py  → OpenAI/OpenCode SDK provider implementation
  models.py           → Model registry, provider registry, _api_call with retry
  client.py           → chat() and chat_stream() with fallback, tool delta processing
  manager.py          → Model discovery, verification, selection

tools/
  __init__.py         → Auto-loader: TOOLS, TOOL_MAP, TOOL_DEFINITIONS
  runner.py           → Parallel execution (pool), rate limiter (per-session LRU)
  loader.py           → Filesystem scan + dynamic imports
  _path_helpers.py    → Path traversal guard (realpath + commonpath)
  _widget_helpers.py  → Widget ID sanitization + arg validation
  *.py                → Individual tools (DEFINITION + run)

memory/
  database.py         → Connection factory (WAL, busy timeout), init_db
  repositories.py     → 6 repos: Message, Session, ToolCall, WidgetState, Debug, SavedWidget
  migrations.py       → 9 idempotent migrations (001→009)

context/
  context.py          → System prompt builder, context loader, TOOLS.md generator (lazy)

web/
  routers/chat.py     → Streaming POST endpoint (ChatPayload, NDJSON, error classification)
  routers/pages.py    → HTML pages, sidebar, message rendering, model selector
  routers/sessions.py → Rename, delete
  routers/widgets.py  → Widget API (WidgetStatePayload, SaveWidgetPayload)
  routers/debug.py    → Debug info + backend log buffer (_local_only guard)
  services/chat_stream.py
                      → NDJSON stream generator, auto-rename (background)
  services/message_renderer.py
                      → Full HTML message list rendering with widget display
  ui_utils.py         → HTML message rendering (phases, reasoning, tool pills)
  logging.py          → BackendLogHandler (ring buffer on kairos.*)

support/
  config.py           → Environment variables
  compressor.py       → History compression when > 40 msgs / 6k tokens
  background_tasks.py → Auto-rename session via LLM
  handler_cli.py      → CLI commands (/model, /clear, /help)
  paths.py            → Path constants (DATA_DIR, DB_PATH, STATIC_DIR, etc.)
```

---

## `src/api.py`

**Responsibility:** Public facade for the entire backend. Web routers call api.py exclusively; it owns repository singletons and coordinates core/orchestrator + memory.

**Public Interface (19+ functions):**
- `get_repos()` → tuple of 6 repo instances (lazy)
- `ensure_session(session_id)`, `rename_session(...)`, `delete_session(...)`, `get_sessions(limit)`
- `save_message(...)`, `get_session_messages(...)`, `get_history(...)`, `get_tool_history(...)`
- `rebuild_history(...)`, `filter_messages_for_ui(...)`, `match_tools_to_msgs(...)`
- `save_widget_state(...)`, `db_save_widget(...)`, `db_get_widget(...)`, `db_get_widget_versions(...)`, `db_get_widget_by_version(...)`
- `save_debug_info(...)`, `get_debug_info(...)`
- `chat_stream(...)` — delegates to `orchestrator.chat_stream()`

**Depends on:** `src.memory.repositories`, `src.core.orchestrator`, `src.core.history`

---

## `src/core/orchestrator.py`

**Responsibility:** The conversation engine. Manages the full lifecycle from user input to final response.

**Public Interface:**
- `chat_stream(message_user, history, model, session_id, tagged, debug, phases_output, streaming) → Generator`
- `_compress_if_needed(history, model) → list`
- `_save_debug_info(session_id, model, history_before, chain, system_prompt, tool_calls)`

**Depends on:** `src.llm.client`, `src.tools`, `src.context`, `src.compressor`, `src.memory.repositories`

**Key Internals:**
- `_deps` module provides `llm_chat`, `llm_stream`, `build_system_prompt`, `TOOL_MAP` as wired partials.
- Delegates tool loops to `tool_loop.run_tool_loop_streaming()` / `run_tool_loop_sync()`.

---

## `src/core/tool_loop.py`

**Responsibility:** Tool call orchestrator — manages reasoning → tool → response cycles (max 5 turns).

**Public Interface:**
- `run_tool_loop_streaming(...) → Generator` — streaming path
- `run_tool_loop_sync(...) → tuple[str, list]` — synchronous path (CLI)

**Key Internals:**
- `_ToolLoopContext` dataclass: wraps 11 parameters into a single object.
- `_process_tool_turn(...)`, `_process_sync_turn(...)`: single-turn processor.
- `_process_llm_stream(...)`: reads LLM stream, yields content/reasoning/tool_calls.
- `_yield_stream_fallback(...)`: fallback when streaming fails.

**Depends on:** `src.llm.client`, `src.tools.runner`, `src.memory.repositories`

---

## `src/core/history.py`

**Responsibility:** Bridge between raw DB rows and valid LLM message lists.

**Public Interface:**
- `rebuild_history(session_id, model) → list` — reconstructs LLM-ready history from DB
- `filter_messages_for_ui(raw_msgs) → list` — keeps only final assistant message per turn
- `match_tools_to_msgs(msgs, all_tools) → dict` — associates tools with messages chronologically

**Depends on:** `src.memory.repositories`, `src.context`

---

## `src/core/chat_sync.py`

**Responsibility:** Synchronous chat wrapper (CLI path).

**Public Interface:**
- `chat(message, history, model) → str` — calls `llm_chat`, returns response content

**Depends on:** `src.core._deps`

---

## `src/core/_deps.py`

**Responsibility:** Central dependency wiring. Avoids circular imports.

**Exports (functools.partial):**
- `llm_chat = partial(client.chat, ...)`
- `llm_stream = partial(client.chat_stream, ...)`
- `build_system_prompt = partial(context.build_system_prompt, ...)`
- `TOOL_MAP = src.tools.TOOL_MAP`

---

## `src/llm/protocol.py`

**Responsibility:** LLM Provider Protocol definition.

**Public Interface:**
- `class LLMProvider(Protocol)` — `chat()`, `chat_stream()`, `list_models()`

**Depends on:** nothing

---

## `src/llm/openai_provider.py`

**Responsibility:** OpenAI/OpenCode SDK adapter.

**Public Interface:**
- `class OpenAIProvider` — implements `LLMProvider`
- `OpenAIProvider.list_models() → list[str]`
- `_get_provider() → OpenAI` — lazy singleton

**Depends on:** `config`

---

## `src/llm/models.py`

**Responsibility:** Model registry, provider registry, retry logic.

**Public Interface:**
- `PRIORITY`, `FALLBACK_MODEL`, `FREE_MODELS`, `PAID_MODELS`, `PREFERRED` — constants
- `register_provider(name, provider_class)` — post-import registration
- `_api_call(**kwargs)` — wrapper with exponential backoff
- `_switch_model(model) → str` — fallback model selector
- `_run_with_augmented_backoff(model, messages, **kwargs)` — with tool call limiting

**Depends on:** `config`

---

## `src/llm/client.py`

**Responsibility:** Mid-level LLM interface. Coordinates model fallback, streaming token handling, tool delta processing.

**Public Interface:**
- `chat(messages, model, **kwargs) → Choice` — single response
- `chat_stream(messages, model, reasoning_output, tagged, tool_calls_output, **kwargs) → Generator`
- `_update_system_prompt(messages, model)` — refreshes system prompt on model switch

**Depends on:** `src.llm.models`, `src.llm.manager`, `src.context`

---

## `src/llm/manager.py`

**Responsibility:** Model lifecycle management.

**Public Interface:**
- `get_default_model() → str` — selects from priority list
- `get_models()`, `get_free_models()`, `get_paid_models()` — API model lists
- `get_verified_models() → list` — health-checked free models
- `verify_model(model) → bool` — tests model with a minimal prompt
- `_mark_and_refresh(model) → str` — marks failed, returns alternative

**Depends on:** `src.llm.models`, `config`

---

## `src/tools/__init__.py`

**Responsibility:** Tool auto-discovery and registration.

**Public Interface:**
- `TOOLS` — list with single `execute_action` schema for LLM API
- `TOOL_MAP` — dict mapping action_name → run function
- `TOOL_DEFINITIONS` — dict mapping action_name → full DEFINITION dict

**Depends on:** `src.tools.loader` (invoked at module init)

---

## `src/tools/runner.py`

**Responsibility:** Execute tool calls in parallel and yield streaming events.

**Public Interface:**
- `run_parallel_tools(tool_calls, session_id, turn, history, tool_detail, used_tools, phase_tool_ids, tagged, tool_map) → Generator`

**Internals:**
- `_session_rate` — dict with per-session rate limiting (30 calls / 10s window, LRU eviction)
- `_rate_lock` — threading.Lock for thread-safe rate checking

**Depends on:** `src.memory.repositories`

---

## `src/memory/database.py`

**Responsibility:** SQLite connection factory and schema initialization.

**Public Interface:**
- `get_conn() → Connection` — WAL mode, busy timeout, `PooledConnection` wrapper
- `init_db()` — creates tables, runs all migrations, enables foreign keys

**Depends on:** `config`

---

## `src/memory/repositories.py`

**Responsibility:** All DB CRUD operations in 6 classes.

**Public Interface:**
- `class _BaseRepository` — `_conn`, `_transaction()` context manager with rollback
- `class MessageRepository` — `save()`, `save_record()`, `get_session_messages()`, `delete_session_messages()`
- `class SessionRepository` — `ensure()`, `rename()`, `delete()`, `get_all()`, `check_should_rename()`
- `class ToolCallRepository` — `log()`, `get_history()`, `delete_session_tool_calls()`
- `class WidgetStateRepository` — `save_state()`, `get_states()`, `delete_session_widget_states()`
- `class SavedWidgetRepository` — `save()`, `get()`, `get_versions()`, `get_by_version()`
- `class DebugRepository` — `save_info()`, `get_info()`, `delete_session_debug()`

**Depends on:** `src.memory.database`

---

## `src/memory/migrations.py`

**Responsibility:** Schema migrations (idempotent, sequential).

**Migrations (9 total):**
- `_migration_001_initial_schema` → `_migration_009_add_indexes`
- Each uses `IF NOT EXISTS` / `try/except OperationalError` for idempotency
- Last three: add FK references + indexes on all `session_id` columns

**Depends on:** `src.memory.database`

---

## `src/context.py`

**Responsibility:** System prompt assembly and context file management.

**Public Interface:**
- `build_system_prompt(model) → dict` — `{role: "system", content: ...}`
- `load_context() → str` — concatenated SOUL + MEMORY + AGENTS
- `_build_tools_md() → str` — generates TOOLS.md from TOOL_DEFINITIONS (lazy import of `src.tools`)

**Depends on:** `src.tools` (for TOOL_DEFINITIONS), `src.paths`

---

## `web/routers/chat.py`

**Responsibility:** The main streaming endpoint.

**Public Interface:**
- `POST /chat/{session_id}` — NDJSON stream (accepts `ChatPayload`: message, model, tagged)

**Internals:**
- Validates input via Pydantic `ChatPayload`
- Rebuilds history from DB via `api.py`
- Delegates to `services/chat_stream.py` for NDJSON generation
- Classifies errors (rate_limit, timeout, network, model, empty_response)
- Saves assistant message + debug info + triggers auto-rename

**Depends on:** `src.api`, `src.background_tasks`

---

## `web/routers/pages.py`

**Responsibility:** All HTML page routes.

**Public Interface:**
- `GET /` — new chat page
- `GET /sessions/{session_id}` — existing chat page
- `GET /sidebar` — session list for sidebar
- `GET /sessions/{session_id}/messages` — message list via `message_renderer`
- `GET /new-session` — generates UUID

**Depends on:** `src.api`, `web.services.message_renderer`, `web.ui_utils`

---

## `web/routers/sessions.py`

**Responsibility:** Session CRUD.

**Public Interface:**
- `POST /sessions/{session_id}/rename` — rename session
- `DELETE /sessions/{session_id}` — delete session (cascades all data)

**Depends on:** `src.api`

---

## `web/routers/widgets.py`

**Responsibility:** Widget state and versioned widget API.

**Public Interface:**
- `POST /sessions/{session_id}/widgets/{widget_id}/state` — save widget state (`WidgetStatePayload`)
- `GET /sessions/{session_id}/widgets/{widget_id}/code` — get widget code
- `POST /sessions/{session_id}/widgets/{widget_id}/save` — save official widget (`SaveWidgetPayload`)
- `GET /sessions/{session_id}/widgets/{widget_id}/versions` — list versions
- `GET /sessions/{session_id}/widgets/{widget_id}/versions/{version}/code` — get specific version
- All widget endpoints are scoped under `/sessions/{session_id}/widgets/`

**Depends on:** `src.api`

---

## `web/routers/debug.py`

**Responsibility:** Debug information and backend log capture.

**Public Interface:**
- `GET /sessions/{session_id}/debug` — debug snapshot JSON
- `GET /debug/backend-logs` — recent backend log entries

**Internals:**
- `_local_only` guard (skipped when `TESTING=true`)
- `BackendLogHandler` in `web/logging.py`: captures `kairos.*` logger into a ring buffer

**Depends on:** `src.api`, `web.logging`

---

## `web/services/chat_stream.py`

**Responsibility:** NDJSON stream generation.

**Public Interface:**
- `StreamState` — dataclass for accumulated stream state
- `generate_stream(session_id, message_user, model, background_task) → StreamingResponse`
- `_classify_error(e) → str` — error type classification
- `_handle_token(...)` — accumulates token stream, yields typed NDJSON events

**Depends on:** `src.api`, `src.background_tasks`

---

## `web/services/message_renderer.py`

**Responsibility:** Full HTML message list rendering.

**Public Interface:**
- `render_session_messages(session_id) → str` — returns complete HTML for all session messages

**Internals:**
- Loads all messages + tool calls, matches tools to messages, renders with phases and widget pills

**Depends on:** `src.api`, `web.ui_utils`

---

## `web/ui_utils.py`

**Responsibility:** HTML rendering primitives for messages.

**Public Interface:**
- `render_msg_with_phases(msg, tool_match) → str` — full HTML for a single message
- Individual phase renderers (reasoning with toggle, content, tool pills)

---

## Dependency Direction

```
entry (cli.py, web/server.py)
  ↓
api (src/api.py)
  ↓
core (orchestrator, tool_loop, chat_sync, history)
  ↓
llm + tools + memory + context
  ↓
config (config.py, paths.py, .env)
```

The web layer depends on api.py. api.py depends on core. Core depends on llm, tools, memory, context. All depend on config. There are no circular dependencies.
