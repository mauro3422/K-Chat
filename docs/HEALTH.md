# Code Health Analysis

This document analyzes the current codebase against SOLID principles and the project's "Legos" philosophy, identifying concrete issues and recommended fixes.

## Summary

| Grade | Area |
|-------|------|
| A | Tools auto-registry, widget system, memory schema, migrations, error classification, core orchestrator split, save_message() dataclass |
| B | LLM abstraction, web routers separation, context decoupling |
| C | — |
| D | — |

All P1–P3 items completed in the original analysis. The codebase is in a healthier state, but the current work has focused on reducing compatibility seams and documenting the remaining ones clearly.

### Bug fixes applied post-analysis

- **Messages disappearing during streaming**: Fixed three root causes — (1) frontend `AbortController` unconditionally removed assistant divs even with content, (2) frontend catch block retried on any JS error destroying already-rendered messages, (3) backend generator did not persist assistant messages when the client aborted the fetch (GeneratorExit before save). Added structured `try...except...finally` save in `web/services/chat_stream.py` and guard conditions in `web/static/modules/chat-form.js`.
- **Stress test coverage**: Added `tests/test_stream_abort_persistence.py` (5 cases covering GeneratorExit, empty response, partial reasoning, and consecutive streams) and `tests/test-stress-stream-abort.js` (8 assertions simulating full frontend abort scenario). All tests pass.

---

## 1. Single Responsibility Principle (SRP)

### ~~Issue: `src/core/orchestrator.py` is a god file (280 lines)~~ ✅ Fixed

Split into:
- `src/core/chat_sync.py` — simple sync wrapper
- `src/core/tool_loop.py` — streaming and sync tool loops
- `src/core/orchestrator.py` — generator setup, compression, debug (75 lines)

### ~~Issue: `web/routers/chat.py` mixes concerns (103 lines)~~ ✅ Fixed

Extracted to `web/services/chat_stream.py` (77 lines). The router now only validates input and returns `StreamingResponse`.

### ~~Issue: `web/routers/pages.py` mixes routing + rendering + business logic (145 lines)~~ ✅ Fixed

Extracted to `web/services/message_renderer.py`. The router now handles routes and model discovery only (87 lines).

### ~~Issue: `src/memory/database.py` is 181 lines with inline migrations~~ ✅ Fixed

Extracted to `src/memory/migrations.py` (198 lines, 9 numbered migrations). `database.py` is now 33 lines.

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

Both files now use regular imports. The remaining `_deps` seam is narrow and mostly exists for compatibility/test patching; the runtime should be treated as the direct imports in `src.llm.client` and `src.core.tool_loop`.

---

## 4. Interface Segregation Principle (ISP)

### Issue: `save_message()` has 11 parameters

```python
def save_message(session_id, role, content, model=None, reasoning="", phases="[]",
                 prompt_tokens=0, completion_tokens=0, total_tokens=0,
                 tool_calls=None, tool_call_id=None):
```

~~Callers often pass many defaults.~~ ✅ Fixed

`save_message()` now accepts either positional/keyword arguments (backward compatible) or a `MessageRecord` dataclass as a single argument. All existing callers continue to work unchanged.

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

### ~~Issue: `src/llm/models.py` depends on `src.context`~~ ✅ Fixed

`_update_system_prompt` se movió de `models.py` a `client.py`. `models.py` ya no importa `src.context`.

### Issue: `src/compressor.py` imports `src.llm.chat` directly

It bypasses the `client.py` abstraction layer.

**Recommendation:** Import from `src.llm.client` or, better, accept a `chat_fn` callable as parameter:
```python
def compress_history(history: list, model: str, chat_fn=llm_chat) -> None:
```

This makes the compressor testable without patching global imports.

### Issue: `src/background_tasks.py` depends on `src.llm.chat`

Same problem — it should receive a callable, not import directly.

---

## 6. "Legos" Violations

### File that should not exist

| File | Why | Fix |
|------|-----|-----|
| ~~`src/tool_runner.py`~~ | ~~1-line re-export~~ | ~~Delete~~ ✅ |
| ~~`web/routers/__init__.py`~~ | ~~Only groups imports~~ | ~~Delete, use auto-discovery~~ ✅ |
| `src/handler_cli.py` | Entry concern in core | Move to `src/cli/` or keep but rename to `cli_commands.py` |

### Inline imports (code smell) — mostly fixed ✅

- `web/routers/pages.py`: imports moved to top
- `src/core/orchestrator.py`: imports moved to top
- Remaining inline imports are justified for lazy-loading or circular-dependency breaking.

### Mixed language in code — mostly fixed ✅

All log messages, error strings, docstrings and code comments have been translated to English. UI text remains in the user's language.

---

## 7. Database Layer Health

### Issue: No connection pool

`get_conn()` creates a new connection per call. With WAL mode this is acceptable for SQLite, but each function opens/closes a connection.

**Recommendation:** For now, acceptable. If concurrency increases, switch to a connection pool or a single persistent connection with proper locking.

### Issue: Migration logic mixed with schema creation

The `init_db()` function does both:
1. `CREATE TABLE IF NOT EXISTS`
2. `ALTER TABLE ADD COLUMN` (6 times, wrapped in try/except)
3. Full table migration for `saved_widgets` (86 lines)

**Recommendation:** Extract to `src/memory/migrations.py`:
```python
# migrations.py
MIGRATIONS = [
    _migration_001_initial_schema,
    _migration_002_add_reasoning,
    _migration_003_add_turn,
    _migration_004_add_phases,
    _migration_005_add_tool_calls,
    _migration_006_add_tool_call_id,
    _migration_007_saved_widgets_global,
    _migration_008_add_token_counts,
]

def init_db():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER)")
    cursor.execute("SELECT version FROM schema_version")
    row = cursor.fetchone()
    current = row[0] if row else 0
    for i, migration in enumerate(MIGRATIONS[current:], start=current+1):
        migration(cursor)
        cursor.execute("INSERT OR REPLACE INTO schema_version (version) VALUES (?)", (i,))
        conn.commit()
```

---

## 8. Error Handling Health

### ~~Issue: Error classification is duplicated~~ ✅ Fixed

Extracted `StreamError` class and `_classify_error()` to `web/services/chat_stream.py`.

### Issue: `except Exception as e` without context

Multiple places catch generic exceptions and only log:
- `src/memory/database.py` in ALTER TABLE blocks
- `src/compressor.py`
- `src/background_tasks.py`

**Recommendation:** Catch specific exceptions where possible. For the `ALTER TABLE` case, catching `sqlite3.OperationalError` is correct. For other cases, add more context to the log.

---

## 9. Testability Issues

### ~~Issue: `src/core/orchestrator.py` is hard to unit test~~ ✅ Fixed

The orchestrator was split into `chat_sync.py`, `tool_loop.py`, and `orchestrator.py`. Tests now patch specific functions on the module namespace (e.g., `src.core.llm_stream`, `src.core.TOOL_MAP`) directly. All 102 Python tests pass.

### ~~Issue: `src/llm/__init__.py` mocking hack makes tests fragile~~ ✅ Fixed

Both `src/core/__init__.py` and `src/llm/__init__.py` were converted to regular imports. Tests patch `src.core.llm_chat` and `src.core.llm_stream` directly on the module. The ModuleType property hacks were removed completely.

---

## 10. Recommended Refactoring Priority

### ✅ Done

1. **Delete `src/tool_runner.py`**
2. **Move inline imports to top** — `pages.py`, `orchestrator.py`
3. **Extract `src/memory/migrations.py`** — separate from `database.py`
4. **Translate remaining Spanish logs/comments**
5. **Split `src/core/orchestrator.py`** into `chat_sync.py`, `tool_loop.py`
6. **Extract error classification** to `web/services/chat_stream.py`
7. **Extract `StreamBuilder`** from `web/routers/chat.py` to `web/services/chat_stream.py`
8. **Extract message renderer** from `web/routers/pages.py` to `web/services/message_renderer.py`
9. **Split `widget-system.js`** into `web/static/modules/widgets/` folder
10. **Auto-discover web routers** — scan `web/routers/*.py` instead of manual imports in `server.py`
11. **Remove `web/routers/__init__.py`** — replaced by auto-discovery
12. **Remove `src/llm/models.py` → `src.context` dependency**
13. **Use dataclass for `save_message()`**
14. **Add stream-abort stress tests** — `tests/test_stream_abort_persistence.py` (5 Python cases) and `tests/test-stress-stream-abort.js` (8 JS assertions) verify partial message persistence and DOM preservation on client abort.

### P3 — High impact, higher risk

15. ~~**Remove ModuleType property hacks** from `src/core/__init__.py` and `src/llm/__init__.py`~~ ✅ Done
16. ~~**Add connection pooling** to `src/memory/database.py`~~ ✅ Done
17. ~~**Add type hints across all public interfaces**~~ ✅ Done

---

## Appendix: Dependency Graph (Current)

```
cli.py ──────┐
             ▼
web/server.py ──► web/routers/* ──► web/ui_utils.py
             │                       │
             │                       ▼
             │                 src/core/orchestrator.py
             │                 src/core/chat_sync.py
             │                 src/core/tool_loop.py
             │                       │
             │         ┌─────────────┼─────────────┐
             │         ▼             ▼             ▼
             │    src/llm/      src/tools/    src/memory/
             │    client.py     runner.py       database.py
             │    manager.py    *.py            migrations.py
             │    models.py                     message.py
             │                                  session.py
             │                                  widget.py
             │                                  saved_widgets.py
             │                                  debug.py
             │
             └────► src/context.py ──► src/tools/__init__.py
                    src/compressor.py ──► src.llm.client.py
                    src/background_tasks.py ──► src.llm.chat
```

The graph shows the web layer depends on core, which depends on llm/tools/memory. Context depends on tools. This is mostly clean. ~~The remaining problematic cross-dependencies are:~~
- ~~`src/compressor.py` → `src.llm.chat` (should use abstraction)~~ ✅ Fixed — now imports from `src.llm.client`
- ~~`src/background_tasks.py` → `src.llm.chat` (should use abstraction)~~ ✅ Fixed — now imports from `src.llm.client`
