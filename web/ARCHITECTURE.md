# web/ — Architecture

> Concise overview of the web layer (FastAPI + Jinja2 + HTMX + NDJSON streaming).

---

## 1. Files at a glance

### Entry points

| File | Responsibility |
|------|----------------|
| `server.py` | Exposes the FastAPI app via `create_app()` for ASGI import |
| `app_factory.py` | FastAPI app factory, lifespan (SearXNG, DB init, model discovery), middlewares, exception handlers, auto-discovery of routers |
| `dev_server.py` | Development launcher with port-freeing helper |
| `logging_handler.py` | In-memory ring buffer (`BackendLogHandler`) for backend logs exposed via `/debug/backend-logs` |
| `ui_utils.py` | Pure HTML rendering helpers for chat messages (phases, reasoning, tool calls, timestamps) |

### Routers (9)

| File | Routes | Responsibility |
|------|--------|----------------|
| `routers/health.py` | `GET /health` | DB + LLM provider + cluster health check |
| `routers/chat.py` | `POST /chat/{session_id}` | Accepts message + files, returns NDJSON stream, background tasks |
| `routers/sessions.py` | `POST .../rename`, `POST .../delete` | Session management |
| `routers/widgets.py` | `GET/POST .../widgets/*` | CRUD for HTML widgets: state, code, versions, save |
| `routers/skills.py` | `GET /api/skills` | Lists skills from the catalog |
| `routers/asr.py` | `POST /api/asr/transcribe`, `WS /api/asr/stream` | ASR transcription + streaming |
| `routers/logs.py` | `GET/POST /api/logs/` | Client log ingestion + server log retrieval |
| `routers/pages.py` | `GET /`, `/sessions/{id}`, `/models/availability` | HTML pages (Jinja2 templates) |
| `routers/debug.py` | `GET /rate-limits`, `/debug/*` | Local-only debug info |

### Services (16)

| File | Responsibility |
|------|----------------|
| `services/chat_stream.py` | `build_stream_generator` — orchestrates LLM + tools + persistence + loop detection + retry |
| `services/chat_stream_contract.py` | `StreamGeneratorDeps` dataclass |
| `services/stream_contract.py` | `build_stream_event` / `serialize_stream_event` — NDJSON schema |
| `services/stream_state.py` | `StreamState` — accumulates text/reasoning, periodic persistence |
| `services/stream_retry_handler.py` | `StreamRetryHandler` — recovery with continuation |
| `services/stream_error_classifier.py` | Classifies errors (rate_limit, timeout, network, tool_error, model, unknown) |
| `services/message_persister.py` | `save_assistant_message` + dedup of phases |
| `services/message_persister_contract.py` | `MessagePersisterDeps` dataclass |
| `services/message_renderer.py` | `render_session_messages` + widget states |
| `services/message_renderer_contract.py` | `MessageRenderDeps` dataclass |
| `services/widget_contract.py` | `normalize_inline_widget_code` / `extract_inline_widget_states` |
| `services/loop_detector.py` | `LoopDetector` — detects token/phrase loops |
| `services/model_catalog.py` | `format_model_label` / `get_model_metadata` |
| `services/asr_service.py` | `transcribe_audio` — Google Speech API + ffmpeg |
| `services/file_logger.py` | `JsonlHandler` — structured logging to rotating JSONL |
| `services/protocols.py` | `StreamGeneratorProtocol`, `MessagePersisterProtocol`, `MessageRendererProtocol` |

### Static

| File | Responsibility |
|------|----------------|
| `static/app.js` | Bundled frontend entry point |

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
| 1 | `rate_limit_middleware` | Per-IP sliding window (default 60 req/min, configurable). Only applies to POST/PUT/DELETE/PATCH. Skips GET/HEAD/OPTIONS. Returns 429 on exceeded. |
| 2 | `csp_middleware` | Adds `Content-Security-Policy` header to every response (`default-src 'self'`, `script-src 'self'`, `style-src 'self' 'unsafe-inline'`). |
| 3 | `add_no_cache_headers` | Sets `Cache-Control: no-cache, no-store, must-revalidate` on `/static` responses. |

**Exception handlers** (not middlewares, but in the same layer):

| Handler | Status | Behavior |
|---------|--------|----------|
| `ServiceException` | dynamic | Returns `exc.detail` with `exc.status_code` |
| `404` | 404 | JSON `{"detail": "Not found"}` |
| `RequestValidationError` | 422 | JSON with str representation |
| `Exception` (catch-all) | 500 | Logs error detail, returns `{"detail": "Internal server error"}` |

---

## 4. Chat request flow (HTTP → Streaming)

```
Client POST /chat/{session_id}
  │
  ▼
chat.py:chat()
  ├─ Validates session_id and message
  ├─ ensure_session(session_id)              # DB
  ├─ rebuild_history(session_id, model, messages_repo=...)
  ├─ db_save_message(MessageRecord(...))     # persists user msg
  │
  ▼
build_stream_generator(deps)
  ├─ Returns a closure generate()
  │
  ▼
StreamingResponse(generate(), media_type="application/x-ndjson")
  │
  ├─ For each (tipo, token) from chat_stream():
  │     ├─ serialized via stream_contract.py
  │     └─ frontend parses the same event set through stream-contract.js
  │
  ├─ On completion:
  │     ├─ message_persister.save_assistant_message()
  │     └─ background_tasks.add_task(auto_rename_session)
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
| Uvicorn | `dev_server.py` |
| `src.api` | Domain modules for sessions, messages, widgets, debug, tools, history, skills, ASR |
| `sqlite3` | `health.py` (read-only DB ping) |
| `dependencies.manage` | `app_factory.py` (SearXNG lifecycle) |

### Internal (`web/`)

```
server.py              ← importlib.imports all routers
app_factory.py         ← server.py
logging_handler.py     ← debug.py
ui_utils.py            ← message_renderer.py (via render_msg_with_phases)
chat.py                ← chat_stream.py
chat_stream.py         ← message_persister.py, stream_error_classifier.py,
                          stream_contract.py, chat_stream_contract.py,
                          stream_state.py, stream_retry_handler.py,
                          loop_detector.py, model_catalog.py
message_renderer.py    ← message_renderer_contract.py, widget_contract.py
```

---

## 6. What's well done

- **Auto-discovery**: zero-config router registration; drop a file and it works.
- **Error resilience**: middlewares catch and format all exceptions; stream errors are classified and user-friendly.
- **Partial save on interrupt**: `finally` block ensures incomplete streams still persist.
- **Contracts desacoplados**: dependencies are explicit dataclasses (`StreamGeneratorDeps`, `MessagePersisterDeps`, `MessageRenderDeps`), not implicit imports.
- **Debug layer**: local-only guard on debug endpoints; in-memory log buffer avoids disk I/O.
- **CSP + rate limiting**: security basics covered at the middleware layer.
- **Streaming with heartbeat**: 20s heartbeat + loop detector prevent silent failures.
- **Protocol isolation**: `protocols.py` defines abstract interfaces for stream, persistence, and rendering — swapable by design.

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
| **`health.py` builds a large snapshot from loose app state** | The endpoint is still easy to drift as new state fields appear; a dedicated typed snapshot helper would make the response contract easier to evolve. |
| **No tests in `web/`** | No test files found; the architecture would benefit from integration tests for the streaming flow. |
| **CSP `unsafe-inline`** | Required for inline scripts/styles but weakens XSS protection; consider nonces or hashes. |

(End of file)
