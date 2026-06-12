# web/ - Architecture

> Concise overview of the web layer (FastAPI + Jinja2 + HTMX + NDJSON streaming).

---

## 1. Files at a glance

| File | Responsibility |
|------|----------------|
| `server.py` | Exposes the FastAPI app object for ASGI import |
| `app_factory.py` | FastAPI app factory, lifespan, middlewares, exception handlers, auto-discovery of routers |
| `dev_server.py` | Development launcher and optional port-freeing helper |
| `logging.py` | In-memory ring buffer (`BackendLogHandler`) for backend logs exposed via `/debug/backend-logs` |
| `ui_utils.py` | Pure HTML rendering helpers for chat messages (phases, reasoning, tool calls, timestamps) |
| `routers/pages.py` | Serves HTML pages: `/`, `/sessions/{id}`, `/sidebar`, `/sessions/{id}/messages` |
| `routers/chat.py` | `POST /chat/{session_id}` — accepts message, returns NDJSON stream |
| `routers/sessions.py` | `POST .../rename`, `POST .../delete` — session management |
| `routers/widgets.py` | CRUD for HTML widgets: state, code, versions, save |
| `routers/debug.py` | `GET .../debug`, `GET /debug/backend-logs` — local-only debug endpoints |
| `routers/health.py` | `GET /health` — DB + LLM provider connectivity check |
| `services/chat_stream.py` | Builds the NDJSON generator that wraps `chat_stream()` and persists on completion/error |
| `services/stream_contract.py` | Shared NDJSON event contract for server-side stream serialization |
| `services/message_persister.py` | Serializes phases + debug info and writes assistant message + debug to DB |
| `services/message_renderer.py` | Renders full session HTML: fetches messages, matches tools, extracts widget code, builds form |
| `services/stream_error_classifier.py` | Pattern-matches error strings into categories (`rate_limit`, `timeout`, `network`, `model`, `unknown`) |
| `static/app.js` | Bundled frontend entry. Assembles the runtime and delegates compatibility globals to bootstraps. |
| `static/modules/widgets/bootstrap.js` | Compatibility bootstrap for `window.KairosWidgets` |
| `static/modules/stream-bootstrap.js` | Compatibility bootstrap for `window.StreamOrchestrator` |
| `static/modules/chat-form-bootstrap.js` | Compatibility bootstrap for `window.KairosForm` |

---

## 2. Auto-discovery of routers

On app creation, `app_factory.py` scans `web/routers/*.py`:

1. `Path(__file__).parent / "routers"` → lists files.
2. Skips: non-`.py`, files starting with `_`.
3. `importlib.import_module(f'web.routers.{mod_name}')`.
4. If `mod.router` exists → `app.include_router(mod.router)`.
5. Errors are logged and silently skipped.

**Result**: Adding a new router file automatically registers its routes — no manual `include_router` calls needed.

---

## 3. Middlewares

Three HTTP middlewares, applied in stack order (outermost first):

| # | Name | What it does |
|---|------|-------------|
| 1 | `rate_limit_middleware` | Per-IP sliding window (default 60 req/min, configurable via `HTTP_RATE_LIMIT`). Skips `/static`. Returns 429 on exceeded. |
| 2 | `csp_middleware` | Adds `Content-Security-Policy` header to every response. |
| 3 | `add_no_cache_headers` | Sets `Cache-Control: no-cache` on `/static` responses. |

**Exception handlers** (not middlewares, but in the same layer):
- `404` → JSON `{"detail": "Not found"}`
- `RequestValidationError` → JSON 422
- `Exception` (catch-all) → JSON 500 + logs error

---

## 4. Chat request flow (HTTP → Streaming)

```
Client POST /chat/{session_id}
  │
  ▼
chat.py:chat()
  ├─ Validates session_id and message
  ├─ ensure_session(session_id)          # DB
  ├─ rebuild_history(session_id, model)  # fetches history
  ├─ db_save_message("user", ...)        # persists user msg
  │
  ▼
chat_stream.py:build_stream_generator()
  ├─ Returns a closure `generate()`
  │
  ▼
StreamingResponse(generate(), media_type="application/x-ndjson")
  │
  ├─ For each (tipo, token) from chat_stream():
  │     ├─ serialized through `web/services/stream_contract.py`
  │     └─ frontend parses the same event set through `web/static/modules/stream-contract.js`
  │
  ├─ On completion:
  │     ├─ message_persister.save_assistant_message()  # writes content + phases + debug to DB
  │     └─ background_tasks.add_task(auto_rename_session)  # async rename
  │
  ├─ On error:
  │     ├─ stream_error_classifier.classify_error() → user-friendly message
  │     └─ yield {"t":"error","d":{"type":..., "message":...}}
  │
  └─ finally: saves partial message if stream was interrupted
```

---

## 5. Dependencies

### External

| Dependency | Used by |
|------------|---------|
| FastAPI | `server.py`, all routers |
| Jinja2 | `pages.py`, `message_renderer.py` |
| Pydantic | `chat.py`, `widgets.py` (payload models) |
| Uvicorn | `server.py` (`__main__`) |
| `src.api` | Backward-compatible facade for routers/services still in transition |
| `src.memory.connection` | `health.py` (DB ping) |
| `dependencies.manage` | `server.py` (SearXNG lifecycle) |

### Internal (`web/`)

```
server.py          ← importlib.imports all routers
logging.py         ← debug.py
ui_utils.py        ← message_renderer.py (via render_msg_with_phases)
chat.py            ← chat_stream.py
chat_stream.py     ← message_persister.py, stream_error_classifier.py, stream_contract.py
message_renderer.py← ui_utils.py
```

`pages.py` and `message_renderer.py` both call `src.api` functions directly — no shared service layer between them.

---

## 6. What's well done

- **Auto-discovery**: zero-config router registration; drop a file and it works.
- **Error resilience**: middlewares catch and format all exceptions; stream errors are classified and user-friendly.
- **Partial save on interrupt**: `finally` block ensures incomplete streams still persist.
- **Separation of concerns**: streaming logic isolated in `services/`; routers are thin.
- **Debug layer**: local-only guard on debug endpoints; in-memory log buffer avoids disk I/O.
- **CSP + rate limiting**: security basics covered at the middleware layer.

---

## 7. What could improve

| Issue | Detail |
|-------|--------|
| **Tight coupling to `src.api`** | Every module imports `src.api` directly — no abstraction layer. Swapping the DB or LLM requires touching every file. |
| **`_rate_limit_store` is global dict** | Not thread-safe with async; in multi-worker deployments each worker has its own store. Consider Redis or `asyncio.Lock`. |
| **`ui_utils.py` builds raw HTML** | `html.escape()` on content but no markdown rendering at this layer — easy to introduce XSS if content assumptions change. |
| **`message_renderer.py` duplicates logic** | Extracts widgets via regex *and* calls `render_msg_with_phases` — widget extraction could be a service. |
| **No auth on `/chat/{session_id}`** | Anyone with a session UUID can post messages. Only rate limiting protects the endpoint. |
| **`_max_backend_logs = 100` hardcoded** | Should be configurable or at least a constant at module level with a clear name. |
| **`health.py` imports at call time** | `from src.memory.connection import get_conn` inside the function — inconsistent with other modules. |
| **No tests in `web/`** | No test files found; the architecture would benefit from integration tests for the streaming flow. |
| **CSP `unsafe-inline`** | Required for inline scripts/styles but weakens XSS protection; consider nonces or hashes. |
