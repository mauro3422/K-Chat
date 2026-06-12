# K-Chat Contract Map

This document is the working map for turning K-Chat into a stricter "legos"
system. It focuses on contracts between layers, not on isolated bugs.

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
| HTTP chat stream | `web/services/chat_stream.py`, `web/services/stream_contract.py`, `web/routers/chat.py` | `web/static/modules/*`, browser UI | Stream event shape used to be implicit; server and client now share the event contract modules | Shared event schema + contract tests |
| Assistant/tool persistence | `src.api.messages`, `src.memory.repos.*` | `src/core`, `web/services/message_persister.py`, tools | `src/tools/_tool_persister.py` used raw SQL; now the combined write path lives in `ToolCallRepository.record_execution()` | One persistence path through repositories/facade |
| Tool execution loop | `src/core/tool_loop.py`, `src/constants.py` | `src/core/orchestrator.py`, `src/core/chat_sync.py`, `src.tools.runner` | `max_turns` and loop policy are duplicated in more than one place | Single loop policy module with shared constants |
| LLM selection and fallback | `src/llm/manager.py`, `src/llm/models.py` | `src.core`, `src.api.chat`, `src.compressor`, `src.background_tasks` | `_deps.py` wires hidden partials; fallback policy is split | Explicit provider/fallback interface |
| API facade | `src/api/__init__.py`, `src/api/*` | `web/routers/*`, `web/services/*`, CLI | Facade is now a compatibility layer; most internal callers use domain modules directly | Split by domain contracts, not by file growth |
| Widget rendering/state | `web/static/modules/content-handler.js`, `web/services/message_renderer.py`, `web/services/widget_contract.py`, `web/static/modules/widgets/contract.js`, `src.memory.repos.widget_state_repository` | browser, DB, tool outputs | Render state, widget code, and widget versions were split across Python and JS with no shared schema | Formal widget contract with version/state fields |
| Retry / abort / timeout | `web/static/modules/retry-handler.js`, `web/static/modules/stream-orchestrator.js`, `web/services/chat_stream.py` | browser stream handling, server stream cleanup | Retry state used to be a singleton; now it is held by `RetryController` instances per stream | One stream lifecycle policy and isolated retry state |
| Frontend module state | `web/static/modules/*` | browser entry points, tests | Several modules rely on globals on `window` for compatibility | Reduce globals to compatibility wrappers only |
| Database lifecycle | `src/memory/database.py`, `src/memory/migrations.py`, `src/memory/repos/*` | all persistence paths | Connection management, init, and migrations are concentrated in one module | Separate lifecycle, schema, and repository responsibilities |

## Contract Details

## Public Function Map

These are the functions and objects that should be treated as stable entry
points during refactors. Not every helper needs a written contract, but these
do because many modules depend on them.

### Backend entry points

| Function | Contract |
|---|---|
| `src.api.chat_stream(...)` | Main backend conversation generator. Must preserve history mutation, debug snapshot behavior, and streaming token shape. |
| `src.api.save_message(...)` | Canonical message write path. Must accept `MessageRecord` or legacy args. |
| `src.api.get_session_messages(...)` | Session history read path for UI rendering. |
| `src.api.rebuild_history(...)` | Reconstructs LLM-ready history from DB state. |
| `src.api.filter_messages_for_ui(...)` | Produces UI-safe message list. |
| `src.api.match_tools_to_msgs(...)` | Associates tool calls with assistant turns. |
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
| `web.services.message_persister.save_assistant_message(...)` | Final assistant persistence for web streams. |
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
- `src/constants.py` now owns `MAX_TOOL_TURNS` and the tool-runner heartbeat interval.

### 4. LLM Routing

**Shape today**
- Model choice, fallback, verification, and provider wiring are scattered across `src/llm/*`, `src/core/_deps.py`, and call sites.

**What must stay true**
- One place decides the active model and fallback chain.
- All callers should depend on the same interface for chat and stream.

**Recommended seam**
- Expose a narrow provider/fallback service.
- Remove hidden partial wiring where a function can accept explicit dependencies instead.

### 5. API Facade

**Shape today**
- The facade is now a compatibility surface, not the preferred import path.
- Some internal modules already import domain modules directly.

**What must stay true**
- Web code should not touch repositories directly.
- Facade functions should be grouped by domain, and the flat export pile should keep shrinking.

**Recommended seam**
- Keep the `__init__` re-export file as a compatibility layer only.
- Prefer direct imports from `src.api.chat`, `src.api.session`, `src.api.messages`, `src.api.history`, `src.api.tools`, `src.api.widgets`, `src.api.debug`, and `src.api.database`.

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
- `web/static/modules/widgets/index.js` is the pure export surface; `web/static/modules/widgets/bootstrap.js` owns the `window` compatibility install and handler startup.
- `web/static/modules/stream-bootstrap.js` and `web/static/modules/chat-form-bootstrap.js` own the remaining legacy globals.
- Server-side widget HTML rendering should remain consistent with that same identity model.

### 7. Retry / Abort / Timeout

**Shape today**
- Retry state lives in a per-stream controller, with a legacy singleton kept only for compatibility.
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
- Some modules still depend on `window` aliases for compatibility.
- Module-local state and compatibility globals coexist.

**What must stay true**
- Globals should be compatibility shims only.
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
