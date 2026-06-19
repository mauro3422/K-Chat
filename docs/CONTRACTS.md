# K-Chat Contract Map

This document is the working map for turning K-Chat into a stricter "legos"
system. It focuses on contracts between layers, not on isolated bugs.

For the broader architecture audit and prioritized backlog, see `docs/LEGOS_AUDIT.md`.

Use it as the source of truth before refactoring. If a change crosses one of
these boundaries, update the contract first or the change will keep breaking
other parts of the system.

## Goals

- Make every boundary explicit.
- Keep one source of truth per contract.
- Remove hidden state, duplicate persistence paths, and implicit wire formats.
- Add contract tests before deeper refactors.

## System Boundaries

| Boundary | Source of truth | Main consumers | Current seam / risk | Refactor target |
|---|---|---|---|---|
| HTTP chat stream | `web/services/chat_stream.py`, `web/services/stream_contract.py`, `web/routers/chat.py` | `web/src_ts/*` plus the small transition surface in `web/static/modules/*`, browser UI | Stream event shape used to be implicit; server and client now share the event contract modules | Shared event schema + contract tests |
| Assistant/tool persistence | `src.memory.repos.*`, `src.api.messages` | `src/core`, `web/services/message_persister.py`, tools | `src/tools/_tool_persister.py` used raw SQL; `tool_loop.py` now writes assistant tool-turns directly through `MessageRepository` | One persistence path through repositories/modules |
| Tool execution loop | `src/core/tool_loop.py`, `src/constants.py` | `src/core/orchestrator.py`, `src.tools.runner` | `max_turns` and loop policy are duplicated in more than one place | Single loop policy module with shared constants |
| LLM selection and fallback | `src/llm/discovery.py`, `src/llm/verifier.py`, `src/llm/selector.py`, `src/llm/failover.py`, `src/llm/api_call.py` | `src.core`, `src.llm`, `src.compressor`, `src.background_tasks` | Legacy `_deps.py` seam was removed; fallback policy is split | Explicit provider/fallback interface |
| Model metadata catalog | `web/services/model_catalog.py`, `~/.local/share/opencode-delegate/model_registry.json` (or `KAIROS_MODEL_REGISTRY`) | `web/routers/pages.py`, `web/templates/chat.html` | Model selector used to show raw ids only; richer capabilities were not visible | Cached metadata helper with graceful fallback to ids |
| Search backend bootstrap | `dependencies/manage.py`, `web/app_factory.py` | `src.tools.web_search`, app startup | SearXNG auto-start used to install dependencies implicitly on boot | Explicit install flag + graceful startup error |
| API modules | `src/api/*` | `web/routers/*`, `web/services/*`, CLI | Domain modules are the source of truth; the package marker is empty | Split by domain contracts, not by file growth |
| Widget rendering/state | `web/src_ts/streaming/ContentHandler.ts`, `web/services/message_renderer.py`, `web/services/widget_contract.py`, `web/static/modules/widgets/contract.js`, `src.memory.repos.widget_state_repository` | browser, DB, tool outputs | Render state, widget code, and widget versions were split across Python and JS with no shared schema | Formal widget contract with version/state fields |
| Retry / abort / timeout | `web/src_ts/core/RetryHandler.ts`, `web/src_ts/streaming/StreamOrchestrator.ts`, `web/services/chat_stream.py` | browser stream handling, server stream cleanup | Retry state used to be a singleton; now it is held by `RetryController` instances per stream | One stream lifecycle policy and isolated retry state |
| Frontend module state | `web/src_ts/*` and the small transition surface in `web/static/*` | browser entry points, tests | Several modules rely on globals on `window` for transition support | Reduce globals to wrappers only |
| Database lifecycle | `src/memory/connection_pool.py`, `src/memory/db_path.py`, `src/memory/engine_state.py`, `src/memory/schema.py`, `src/memory/migrations.py`, `src/memory/repos/*` | all persistence paths | Connection management, init, and migrations were concentrated in one module; now they are split | Separate lifecycle, schema, and repository responsibilities |

## Contract Details

## Public Function Map

These are the functions and objects that should be treated as stable entry
points during refactors. Not every helper needs a written contract, but these
do because many modules depend on them.

### Backend entry points

| Function | Contract |
|---|---|
| `src.core.orchestrator.chat_stream(...)` | Main backend conversation generator. Must preserve history mutation, debug snapshot behavior, and streaming token shape. |
| `src.core.orchestrator_contract.OrchestratorDeps` | Bundles orchestration hooks so callers do not need to pass every optional dependency separately. |
| `src.api.messages.save_message_record(...)` | Canonical message write path for runtime callers. |
| `src.api.session_contract.SessionOpsDeps` | Bundles session repository and connection injection for cascade deletes and CRUD wiring. |
| `src.api.widgets_contract.WidgetOpsDeps` | Bundles widget state and saved-widget repositories for state/code/version operations. |
| `src.api.debug_contract.DebugOpsDeps` | Bundles debug repository injection for debug payloads and ASR telemetry. |
| `src.core.history_contract.HistoryRebuildDeps` | Bundles the messages repository used to reconstruct LLM-ready history. |
| `src.api.get_session_messages(...)` | Session history read path for UI rendering. |
| `src.core.history.rebuild_history(...)` | Reconstructs LLM-ready history from DB state. |
| `src.core.history.filter_messages_for_ui(...)` | Produces UI-safe message list. |
| `src.core.history.match_tools_to_msgs(...)` | Associates tool calls with assistant turns. |
| `src.api.save_widget_state(...)` / `db_save_widget(...)` | Persist widget runtime state and official widget code. |
| `src.api.get_widget_states(...)` / `db_get_widget(...)` | Read widget state/code for render and version history. |

### Core engine

| Function | Contract |
|---|---|
| `src.core.orchestrator.chat_stream(...)` | Owns turn lifecycle, debug shape, compression hook, and tool loop entry. |
| `src.core.tool_loop.run_tool_loop_streaming(...)` | Streaming loop policy. Must keep turn semantics stable. |
| `src.core.tool_loop.run_tool_loop_sync(...)` | CLI loop policy. Should not diverge from streaming policy unless documented. |
| `src.core.history.rebuild_history(...)` | Converts raw DB rows into LLM-safe messages. |
| `src.core.history.filter_messages_for_ui(...)` | Filters assistant/tool history for HTML rendering. |

### Web stream/render

| Function | Contract |
|---|---|
| `web.services.chat_stream.build_stream_generator(...)` | Wraps backend generator into NDJSON and handles partial save / retry / rename. |
| `web.services.chat_stream_contract.StreamGeneratorDeps` | Bundles the stream hooks injected by the router so the service signature stays smaller. |
| `web.services.stream_state.StreamState` | Owns partial content/reasoning accumulation and periodic-save timing for chat streams. |
| `web.services.message_persister_contract.MessagePersisterDeps` | Optional dependency bundle for assistant message persistence. |
| `web.services.message_persister.save_assistant_message(...)` | Final assistant persistence for web streams. |
| `web.services.message_renderer_contract.MessageRenderDeps` | Optional dependency bundle for server-side session message rendering. |
| `web.services.message_renderer.render_session_messages(...)` | Server-side HTML render for entire session history. |
| `web.ui_utils.render_msg_with_phases(...)` | Renders one message block with reasoning, phases, tools, and timestamp. |

### Frontend stream/render

| Object / function | Contract |
|---|---|
| `KairosStream.on/emit/off` | Event bus for stream events. Event names must stay stable. |
| `executeStreamFetch(...)` | Fetch loop and NDJSON parser. Must emit the same event shape the server produces. |
| `StreamContext` | Owns per-stream frontend state. Must remain isolated per conversation. |
| `registerContentHandler()` | Content render pipeline for tokens and widgets. |
| `KairosWidgets.extract(text)` | Widget extraction and placeholder generation from markdown. |
| `KairosWidgets.reset()` | Clears widget registry for a new stream. |
| `RetryHandler.scheduleRetry(...)` / `resetRetryCount()` | Retry lifecycle. Must remain per-stream, not global shared state. |

### 1. HTTP Chat Stream

**Shape today**
- Backend emits NDJSON events with `t` and `d` through `web/services/stream_contract.py`.
- Frontend parses and validates the same event set through `web/static/modules/stream-contract.js`.
- Frontend consumes reasoning, content, tool_call, heartbeat, and error.
- Partial saves and retry handling happen around the stream loop.

**What must stay true**
- Event names and payload shapes must remain stable.
- Every new event type must be documented and tested on both sides.
- The frontend should reject unknown event formats explicitly, not silently.

**Recommended seam**
- Keep stream formatting in one server module and parsing in one frontend module.
- Add a JSON schema only if the event set grows or needs external consumers.

**Current source of truth**
- `web/services/stream_contract.py`
- `web/static/modules/stream-contract.js`

### 2. Assistant / Tool Persistence

**Shape today**
- User, assistant, tool, and debug data are all persisted separately.
- Some writes go through repositories, others go through raw SQL.

**What must stay true**
- One logical message write should have one canonical code path.
- Tool call logs and tool result messages should be written together or not at all.

**Recommended seam**
- Route all persistence through `src.memory.repos`.
- Turn `_tool_persister.py` into orchestration only, with no raw SQL.

**Current source of truth**
- `ToolCallRepository.record_execution()` now owns the combined tool-call + tool-message write path.

### 3. Tool Loop

**Shape today**
- Streaming and sync paths exist side by side.
- Turn limits and loop behavior are split across constants and defaults.

**What must stay true**
- There should be one canonical turn limit.
- Tool execution policy should be the same across CLI and web unless documented otherwise.

**Recommended seam**
- Extract a `ToolLoopPolicy` or shared constants module.
- Make the loop entry points thin wrappers around a single policy object.

**Current source of truth**
- `src/constants.py` now owns `MAX_TOOL_TURNS`, `TOOL_OUTPUT_CHUNK_SIZE`, and the tool-runner heartbeat interval.

### 4. LLM Routing

**Shape today**
- Model choice, fallback, verification, and provider wiring are scattered across `src/llm/*` and call sites. The old `_deps.py` seam was removed.

**What must stay true**
- One place decides the active model and fallback chain.
- All callers should depend on the same interface for chat and stream.

**Recommended seam**
- Expose a narrow provider/fallback service.
- Remove hidden partial wiring where a function can accept explicit dependencies instead.

**Current source of truth**
- `src/llm/client.py`
- `src/llm/api_call.py`
- `src/llm/discovery.py`
- `src/llm/verifier.py`
- `src/llm/selector.py`
- `src/llm/failover.py`
- `src/compressor.py` and `src/background_tasks.py` now accept explicit chat callables for their LLM work instead of depending on a module-level import.

### 4b. Model Metadata Catalog

**Shape today**
- The model selector can now show richer labels when a local registry is available.
- The registry provides context window, output limit, modality support, reasoning/tooling flags, costs, and release metadata.

**What must stay true**
- Missing registry data must degrade to raw model ids.
- Selector labels should stay concise and readable in a plain `<select>`.

**Recommended seam**
- Keep metadata loading in one helper with file/env fallback.
- Do not make the UI depend on a network lookup for model labels.

**Current source of truth**
- `web/services/model_catalog.py`
- `~/.local/share/opencode-delegate/model_registry.json`

### 5. API Facade

**Shape today**
- Domain modules are the source of truth.
- The package marker is empty; callers import the specific domain module they need.

**What must stay true**
- Web code should not touch repositories directly.
- Facade functions should be grouped by domain, and the flat export pile should keep shrinking.

**Recommended seam**
- Keep imports pointed at the specific domain module.
- Prefer direct imports from `src.core`, `src.llm`, `src.memory.connection`, `src.memory.schema`, `src.api.session`, `src.api.messages`, `src.api.tools`, `src.api.widgets`, and `src.api.debug`.

**Current source of truth**
- `src.api.*` domain modules are the source of truth; `src.api.__init__` is a package marker only.

### 6. Widgets

**Shape today**
- Widget code can be rendered from model output and also persisted/versioned in DB.
- The frontend does deduplication and incremental rendering.

**What must stay true**
- A widget needs a stable identity, a version, and a state payload.
- The server and client should agree on widget keys and render order.

**Recommended seam**
- Define a widget contract object with key, version, code, state, and source.
- Move widget extraction/render rules into one shared service boundary.

**Current source of truth**
- Frontend widget state lives in `WidgetStateManager`.
- Widget identity comes from the rendered `data-widget-id` / `data-widget-key` pair and the `_code_` prefix for cached code entries.
- Widget code extraction on the server lives in `web/services/widget_contract.py`.
- Widget code normalization and key-prefix helpers on the client live in `web/static/modules/widgets/contract.js`.
- `web/static/modules/widgets/index.js` is the pure export surface; the historical bootstrap files were removed and transition logic now lives in the explicit app/session entrypoints.
- The old `stream-bootstrap.js` and `chat-form-bootstrap.js` entrypoints are gone; the remaining globals are isolated in the current transition surfaces.
- Widget iframes now use `window.__KAIROS_WIDGET_BRIDGE__` for `initialState` and `saveState`; direct globals were removed from the runtime contract.
- Server-side widget HTML rendering should remain consistent with that same identity model.

### 7. Retry / Abort / Timeout

**Shape today**
- Retry state lives in a per-stream controller, with a singleton kept only for bridge support.
- Server-side stream cleanup and partial save happen in the stream wrapper.

**What must stay true**
- Retry count, timeout, and abort policy should be isolated per stream.
- A failed stream should still save a partial assistant message when possible.

**Recommended seam**
- Use a per-stream context object instead of a global retry singleton.
- Keep lifecycle responsibilities in one stream coordinator.

**Current source of truth**
- `RetryController` instances own retry count, max retries, and stream timeout for each stream.

### 8. Frontend Module State

**Shape today**
- Some modules still depend on `window` aliases for bridge support.
- Module-local state and bridge globals coexist.
- The debug panel toggle is now bound via DOM listeners instead of a global `toggleDebug()` hook.
- Sidebar session selection is now handled by delegated clicks in `web/src_ts/core/session/SessionList.ts`; the template no longer carries `onclick="loadSession(...)"`.
- The model selector is bound in the current session UI layer; the template only provides state markup and the persisted value.
- Debug copy buttons are wired via `web/src_ts/core/DebugManager.ts`, not inline handlers.

**What must stay true**
- Globals should be bridge shims only.
- New code should receive state through explicit parameters or module objects.

**Recommended seam**
- Keep `window` assignments only in the bootstrap layer.
- Move the real logic into explicit module exports.

## Refactor Order

1. Stream contract
2. Persistence contract
3. Tool loop policy
4. Retry / abort isolation
5. Widget contract
6. API facade split
7. LLM routing cleanup
8. Frontend global state cleanup

## Contract Tests to Add

- Stream NDJSON schema test.
- Assistant partial-save on abort test.
- Tool call persistence test without raw SQL.
- `max_turns` and heartbeat single-source test.
- Widget render/version/state roundtrip test.
- Retry state isolation test.
- API facade bypass test.

## Working Rule

Before changing a subsystem, answer these three questions:

1. What is the contract?
2. Where is the source of truth?
3. What breaks if this boundary changes?

If the answer is unclear, do not refactor yet. Make the contract explicit first.

## Scope Note

This document is intentionally boundary-first. A full function-by-function map
for every file would be too noisy and would age badly. The goal here is to pin
the public entry points and seams that shape the architecture. For internal
helpers, prefer local tests and code comments over a permanent contract entry.
