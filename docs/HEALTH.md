> ⚠️ This document may lag behind the current version. See [docs/ARCHITECTURE.md](ARCHITECTURE.md) and [docs/MODULES.md](MODULES.md) for the latest.
>
> **Last updated:** 2026-06-18 — Documented: ServiceException (src/api/exceptions.py) replaces HTTPException in API layer; OrchestratorDeps split into 4 sub-dataclasses (LLMDeps/ToolDeps/StorageDeps/RequestStateDeps); MessageRecord canonical type lives in src/memory/types.py; DEFAULT_CONFIG → DI migration in tools and LLM; logbus/model_registry/LLM container/model_state/circuit breaker/rate limit store/embedding cache/reranker/connection pools/event bus/context templates/thread pool now expose explicit configure/reset helpers for cleaner shutdown and tests; `src/tools/runner.py` now accepts sync or async tools via awaitable coercion; `src/tools/*` file/shell tools moved off `asyncio.to_thread` for backend-agnostic execution.

# Code Health Analysis

This document analyzes the current codebase against SOLID principles and the project's "Legos" philosophy, identifying concrete issues and recommended fixes.

## Summary

| Grade | Area |
|-------|------|
| A | Tools auto-registry, widget system, memory schema, migrations, error classification, core orchestrator split, OrchestratorDeps → 4 sub-dataclasses (LLMDeps/ToolDeps/StorageDeps/RequestStateDeps), ServiceException in API layer, save_message_record() explicit contract, DebugInfo dataclass, direct API domain modules, LLMProvider protocol alignment, configurable logbus/model registry/container/model_state/breaker/rate-limit/embedding/reranker/pools/event bus |
| B | Frontend module system, context decoupling |
| C | — |
| D | — |

All P1–P3 items completed. The codebase has been refactored with:
- **DebugInfo dataclass** replacing the mutable dict bag across orchestrator, tool_loop, llm/client, and message_persister
- **API domain modules** (`src/api/`) — web layer imports direct domain modules where appropriate, with `src/api/__init__.py` as package marker only
- **LLMProvider protocol** aligned with OpenAIAdapter implementation

### Bug fixes applied post-analysis

- **Messages disappearing during streaming**: Fixed three root causes — (1) frontend `AbortController` unconditionally removed assistant divs even with content, (2) frontend catch block retried on any JS error destroying already-rendered messages, (3) backend generator did not persist assistant messages when the client aborted the fetch (GeneratorExit before save). Added structured `try...except...finally` save in `web/services/chat_stream.py` and guard conditions in `web/static/modules/chat-form.js`.
- **Stress test coverage**: Added `tests/test_stream_abort_persistence.py` (5 cases covering GeneratorExit, empty response, partial reasoning, and consecutive streams) and `tests/test-stress-stream-abort.js` (8 assertions simulating full frontend abort scenario). All tests pass.

---

## 1. Single Responsibility Principle (SRP)

### ~~Issue: `src/core/orchestrator.py` is a god file (280 lines)~~ ✅ Fixed

Split into:
- `src/core/tool_loop.py` — streaming and sync tool loops
- `src/core/orchestrator.py` — generator setup, compression, debug (75 lines)
- `src/core/orchestrator_contract.py` — `OrchestratorDeps` facade split into 4 focused sub-dataclasses: `LLMDeps`, `ToolDeps`, `StorageDeps`, `RequestStateDeps`

### ~~Issue: `web/routers/chat.py` mixes concerns (103 lines)~~ ✅ Fixed

Extracted to `web/services/chat_stream.py` (77 lines). The router now only validates input and returns `StreamingResponse`.

### ~~Issue: `web/routers/pages.py` mixes routing + rendering + business logic (145 lines)~~ ✅ Fixed

Extracted to `web/services/message_renderer.py`. The router now handles routes and model discovery only (87 lines).

---

## 2. Open/Closed Principle (OCP)

### Good: Tool auto-registry ✅

Adding a tool = new file with `DEFINITION` + `run()`. No edits to existing code.

### ~~Bad: Web routers require manual registration~~ ✅ Fixed

`web/server.py` now auto-discovers routers from `web/routers/*.py` using `importlib`, same pattern as tools. Adding a router = creating a new file with a `router` variable. No edits to existing code.

### ~~Bad: `src/tool_runner.py` is a 1-line facade~~ ✅ Fixed

Deleted. All callers now import `run_parallel_tools` directly from `src.tools.runner`.

---

## 3. Liskov Substitution Principle (LSP)

Mostly not applicable — the codebase is procedural/functional, not class-hierarchical. The one place with "classes" is the `ModuleType` hack.

### ~~Issue: `src/core/__init__.py` and `src/llm/__init__.py` use `sys.modules[__name__].__class__`~~ ✅ Fixed

Both files are now package markers only. The last `_deps` seam was removed after it stopped having runtime consumers; the runtime should be treated as the direct imports in `src.llm.client` and `src.core.tool_loop`.

---

## 4. Interface Segregation Principle (ISP)

### Issue: `save_message_record()` uses an explicit record object

The runtime now writes messages through `save_message_record()` and `MessageRecord`, which removes the old positional-write path. `MessageRecord` canonical type lives in `src/memory/types.py`; `src/memory/repos/protocols.py` imports from there rather than from the implementation.

### Issue: `chat_stream()` takes a `debug: dict` bag

The `debug` dict is populated by the orchestrator, the LLM client, and the tool runner. It's a shared mutable state container.

**Recommendation:** Make `debug` an explicit dataclass:
```python
@dataclass
class DebugInfo:
    model: str = ""
    session_id: str = ""
    reasoning: str = ""
    tool_calls: list = field(default_factory=list)
    history_before: list = field(default_factory=list)
    system_prompt: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    phases: str = "[]"
```

---

## 5. Dependency Inversion Principle (DIP)

### ~~Issue: `src/llm/api_call.py` depends on `src.context`~~ ✅ Fixed

`_update_system_prompt` se mantiene en `client.py`; `api_call.py` solo encapsula la llamada al proveedor.

### In Progress: `DEFAULT_CONFIG` → dependency injection

Tools (`web_search`, `fetch_url`) and LLM modules (`providers`, `discovery`, `retry`) now accept an optional `config` parameter. When provided, it overrides `DEFAULT_CONFIG`. When omitted, the global singleton is used as fallback. This allows tests and alternative configurations to inject custom settings without touching global state.

The remaining module-level state is now easier to control because `config_loader`, `logbus`, `model_registry`, `llm.providers`, `container`, `model_state`, `context.runtime`, `context.templates`, `context.crash_recovery`, `memory.engine_state`, `circuit_breaker`, `rate_limit_state`, `memory.keywords.extractor`, `memory.embeddings.service`, `memory.retrieval.reranker`, `connection_pool`, `memory_pool`, `utils.async_utils`, `web.services.file_logger`, the web app config cache, the SSE `event_bus`, the web app’s HTTP rate-limit store, and the process `gateway` state each expose explicit configure/reset helpers or app-state ownership. The legacy singleton entry points still exist for compatibility, but they are no longer the only way to control lifecycle. `src/tools` now uses a shared thread helper to avoid tying tool retries and file I/O to a single async backend.

### Issue: `src/compressor.py` imports `src.llm.chat` directly

~~It bypasses the `client.py` abstraction layer.~~ ✅ Fixed

`compress_history()` now accepts an optional `chat_fn` callable. The default path imports lazily inside the function, and tests can inject a mock directly.

### Issue: `src/background_tasks.py` depends on `src.llm.chat`

~~Same problem — it should receive a callable, not import directly.~~ ✅ Fixed

`auto_rename_session()` now accepts an optional `chat_fn` callable. The default path imports lazily inside the function, which removes the module-level dependency and makes the seam explicit.

---

## 6. "Legos" Violations

### File that should not exist

| File | Why | Fix |
|------|-----|-----|
| ~~`src/tool_runner.py`~~ | ~~1-line re-export~~ | ~~Delete~~ ✅ |
| ~~`web/routers/__init__.py`~~ | ~~Only groups imports~~ | ~~Delete, use auto-discovery~~ ✅ |
| ~~`src/config.py`~~ | ~~Merged into config_loader.py~~ | ~~Delete~~ ✅ |
| ~~`src/handler_cli.py`~~ | ~~Entry concern in core~~ | ~~Migrated to `src/cli.py`~~ ✅ |

### Inline imports (code smell) — mostly fixed ✅

- `web/routers/pages.py`: imports moved to top
- `src/core/orchestrator.py`: imports moved to top
- Remaining inline imports are justified for lazy-loading or circular-dependency breaking.

### Mixed language in code — mostly fixed ✅

All log messages, error strings, docstrings and code comments have been translated to English. UI text remains in the user's language.

---

## 7. Database Layer Health

### Issue: Connection pools are process-local

`get_conn()` uses a small in-process pool keyed by DB path, and `get_memory_conn()` uses a separate pool for memory.db. That is acceptable for SQLite, but the pools remain process-local state and should be reset at application shutdown. The app factory now does that explicitly.

**Recommendation:** For now, acceptable. If concurrency increases, switch to a longer-lived pool with explicit lifecycle management or a single persistent connection with proper locking.

### Issue: Migration logic mixed with schema creation

The old `init_db()` loop mixed version tracking and migration execution. That loop now lives in `src/memory/migration_runner.py`, while `schema.py` keeps the version-table bootstrap and init orchestration.

**Remaining seam:** if we want the last split, move the version-table bootstrap out of `schema.py` too.

**Recommendation:** keep `schema.py` thin and let `migration_runner.py` own pending migration execution:
```python
from src.memory.migration_runner import run_pending_migrations
```

---

## 8. Error Handling Health

### ~~Issue: Error classification is duplicated~~ ✅ Fixed

Extracted `StreamError` class and `_classify_error()` to `web/services/chat_stream.py`.

### Change: `ServiceException` replaces `HTTPException` in API layer

`src/api/exceptions.py` defines `ServiceException(status_code, detail)`. Domain modules raise this instead of `HTTPException` to avoid coupling to FastAPI. The web layer (`web/app_factory.py`) translates it via `@app.exception_handler(ServiceException)`, returning `JSONResponse` with the proper status code. This keeps domain logic framework-agnostic.

### Issue: `except Exception as e` without context

Multiple places catch generic exceptions and only log:
- `src/memory/schema.py` in ALTER TABLE blocks
- `src/compressor.py`
- `src/background_tasks.py`

**Recommendation:** Catch specific exceptions where possible. For the `ALTER TABLE` case, catching `sqlite3.OperationalError` is correct. For other cases, add more context to the log.

---

## 9. Testability Issues

### ~~Issue: `src/core/orchestrator.py` is hard to unit test~~ ✅ Fixed

The orchestrator/tool loop/sync path were separated during the refactor, and the sync wrapper was later removed once it no longer had runtime consumers. Tests now patch explicit seams or inject callables directly. All 532 Python tests pass.

### ~~Issue: `src/llm/__init__.py` mocking hack makes tests fragile~~ ✅ Fixed

Both `src/core/__init__.py` and `src/llm/__init__.py` are package markers only. The ModuleType property hacks were removed completely, and the remaining compatibility seams are explicit rather than implicit.

---

## 10. Recommended Refactoring Priority

### ✅ Done

1. **Delete `src/tool_runner.py`**
2. **Move inline imports to top** — `pages.py`, `orchestrator.py`
3. **Extract `src/memory/migration_runner.py`** — separate migration execution from schema bootstrap
4. **Translate remaining Spanish logs/comments**
5. **Split `src/core/orchestrator.py`** into explicit orchestration and loop seams
6. **Extract error classification** to `web/services/chat_stream.py`
7. **Extract `StreamBuilder`** from `web/routers/chat.py` to `web/services/chat_stream.py`
8. **Extract message renderer** from `web/routers/pages.py` to `web/services/message_renderer.py`
9. **Split `widget-system.js`** into `web/static/modules/widgets/` folder
10. **Auto-discover web routers** — scan `web/routers/*.py` instead of manual imports in `server.py`
11. **Remove `web/routers/__init__.py`** — replaced by auto-discovery
12. **Remove any `src/llm/models.py` compatibility references**
13. **Use dataclass for `save_message_record()`**
14. **Add stream-abort stress tests** — `tests/test_stream_abort_persistence.py` (5 Python cases) and `tests/test-stress-stream-abort.js` (8 JS assertions) verify partial message persistence and DOM preservation on client abort.

### P3 — High impact, higher risk

15. ~~**Remove ModuleType property hacks** from `src/core/__init__.py` and `src/llm/__init__.py`~~ ✅ Done
16. ~~**Add connection pooling** to `src/memory/connection_pool.py`~~ ✅ Done
17. ~~**Add type hints across all public interfaces**~~ ✅ Done

---

## Appendix: Dependency Graph (Current)

```
src/api/exceptions.py ──→ ServiceException (framework-agnostic)
              │
              ▼
web/app_factory.py ──→ @exception_handler(ServiceException) → JSONResponse

cli.py ──────┐
              ▼
web/server.py ──► web/routers/* ──► web/ui_utils.py
             │                       │
             │                       ▼
             │                 src/core/orchestrator.py
             │                 src/core/tool_loop.py
             │                       │
             │         ┌─────────────┼─────────────┐
             │         ▼             ▼             ▼
             │    src/llm/      src/tools/    src/memory/
             │    client.py     runner.py       repos/
             │    api_call.py   *.py            schema.py
             │    providers.py                  migrations.py
             │    model_state.py                 sqlite_engine.py
             │    discovery.py
             │    verifier.py
             │    selector.py
             │    failover.py
             │
             ├────► src/context/builder.py
             │       ├── src/tools/__init__.py
             │       └── src/paths.py
             ├────► src/compressor.py ──► src.llm.client.py
             └────► src/background_tasks.py ──► src.llm.client
                    src/config_loader.py
```

The graph shows the web layer depends on core, which depends on llm/tools/memory. Context depends on tools and paths. All previously problematic cross-dependencies are resolved with injection parameters or direct lazy imports.
