# Debug: ERR_CONNECTION_REFUSED — 2026-07-03

## Resumen ejecutivo

El servidor FastAPI en `127.0.0.1:8000` cae debido a un `sqlite3.IntegrityError` no manejado en `session_repository.py:ensure()`. El error es una race condition TOCTOU clásica: dos requests concurrentes para el mismo `session_id` ejecutan SELECT + INSERT sin atomicidad, y el segundo INSERT falla con `UNIQUE constraint failed`. La excepción propagada mata el proceso del servidor. El frontend entra en un loop de reintentos que genera spam masivo de `ERR_CONNECTION_REFUSED`.

---

## 1. Logs relevantes extraídos

### 1.1 Crash del servidor (web_server.log)

```
File ".../chat.py", line 82, in chat
    repos = get_repos()
File ".../session_repository.py", line 20, in ensure
    await conn.execute(
sqlite3.IntegrityError: UNIQUE constraint failed: sessions.session_id

/usr/lib/python3.14/concurrent/futures/thread.py:73: RuntimeWarning: coroutine 'run' was never awaited

INFO:     Shutting down
INFO:     connection closed
INFO:     Waiting for connections to close. (CTRL+C to force quit)
INFO:     Waiting for application shutdown.
INFO:     Application shutdown complete.
INFO:     Finished server process [196052]
ERROR:    [Errno 98] error while attempting to bind on address ('127.0.0.1', 8000): [errno 98] address already in use
```

### 1.2 Errores del navegador (consola)

```
POST http://127.0.0.1:8000/chat/76a5e2e8-7ba1-441c-b003-e720e32b8396?model=deepseek-v4-flash → ERR_CONNECTION_REFUSED
GET  http://127.0.0.1:8000/health → ERR_CONNECTION_REFUSED
GET  http://127.0.0.1:8000/api/events/stream → ERR_CONNECTION_REFUSED
GET  http://127.0.0.1:8000/models/availability → ERR_CONNECTION_REFUSED
GET  http://127.0.0.1:8000/api/node/sync/status → ERR_CONNECTION_REFUSED
GET  http://127.0.0.1:8000/api/memory/diagnostics → ERR_CONNECTION_REFUSED
```

El frontend ejecuta reintentos automáticos cada ~2s, generando decenas de requests fallidos.

---

## 2. Cadena causal completa

### 2.1 El bug raíz: Race condition TOCTOU en `session_repository.py:ensure()`

**Archivo:** `src/memory/repos/session_repository.py`, líneas 47-79

```python
async def ensure(self, session_id: str, *, origin_node_id: str = "") -> None:
    async with self._transaction() as conn:
        # CHECK (paso 1)
        cursor = await conn.execute(
            "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
        )
        if not await cursor.fetchone():
            try:
                # INSERT (paso 2) — hueco de race condition aquí
                await conn.execute(
                    "INSERT INTO sessions (session_id, name, created_at, origin_node_id) "
                    "VALUES (?, '', ?, ?)",
                    (session_id, datetime.now().isoformat(), origin_node_id)
                )
            except sqlite3.OperationalError:
                # Fallback para DB pre-migration-025
                await conn.execute(
                    "INSERT INTO sessions (session_id, name, created_at) VALUES (?, '', ?)",
                    (session_id, datetime.now().isoformat())
                )
```

**El problema:** `SELECT` seguido de `INSERT` sin `INSERT OR IGNORE` ni `ON CONFLICT`. Dos requests concurrentes para el mismo `session_id`:

```
Timeline:
  Request A:  SELECT → "no existe" ─────────────── INSERT → OK ✓
  Request B:       SELECT → "no existe" ── INSERT → IntegrityError ✗
```

**Por qué ocurre:** El frontend reenvía el mismo `session_id` en cada reintento. Si el usuario hace clic en reenviar rápidamente, o si el frontend detecta un error de stream y reintenta automáticamente, ambos requests llegan al servidor con el mismo `session_id`.

### 2.2 El `IntegrityError` no está catcheado

El `except` en línea 73 solo atrapa `sqlite3.OperationalError`:

```python
except sqlite3.OperationalError:   # ← Para columnas que no existen (pre-migration)
    ...
```

`sqlite3.IntegrityError` es una subclase de `sqlite3.DatabaseError`, NO de `OperationalError`. Se propaga sin ser atrapada.

### 2.3 La excepción sube por el middleware stack

El traceback completo muestra la cadena:

```
session_repository.py:ensure()     → IntegrityError
    ↓
chat.py:82                         → repos = get_repos() (llama ensure)
    ↓
fastapi/routing.py:328             → run_endpoint_function()
    ↓
starlette/middleware/base.py       → rate_limit_middleware
    ↓
starlette/middleware/base.py       → csp_middleware
    ↓
starlette/middleware/base.py       → add_no_cache_headers
    ↓
starlette/_exception_handler.py    → ExceptionGroup (TaskGroup)
    ↓
uvicorn/protocols/http/h11_impl    → run_asgi()
```

FastAPI/Starlette debería convertir esto en un 500 interno. Pero el `ExceptionGroup` de `anyio.TaskGroup` en Starlette puede causar que la excepción se propague de forma inesperada.

### 2.4 El `RuntimeWarning: coroutine 'run' was never awaited`

```
/usr/lib/python3.14/concurrent/futures/thread.py:73: RuntimeWarning: coroutine 'run' was never awaited
  return fn(*args, **kwargs)
```

**Análisis:** Este warning viene del `ThreadPoolExecutor` interno de Python. Significa que una función que retorna una coroutine fue pasada a `run_in_executor()` como si fuera una función sincrónica. El thread pool ejecuta `fn()` y obtiene un objeto coroutine que nunca se `await`ea.

**Origen probable:** Varios tools tienen `async def run()` (save_memory, manage_memory, etc.). Si alguno de estos es invocado incorrectamente desde un contexto sincrónico que lo pasa al thread pool, se produce este warning. Aunque no es la causa directa del crash, indica un problema de salud del sistema que puede haber contribuido a la inestabilidad.

**Candidatos:**
- `src/tools/edit_file.py:190` — `def run()` (sincrónico, seguro)
- `src/tools/execute_command.py:65` — `def run()` (sincrónico, seguro)
- `src/tools/save_memory.py:101` — `async def run()` (puede ser invocado desde contextos incorrectos)
- `src/tools/manage_memory.py:102` — `async def run()` (mismo caso)

**No es la causa del crash** pero sí un síntoma de que el sistema estaba bajo estrés o tenía un bug secundario de invocación.

### 2.5 El servidor muere y no se recupera

Después del IntegrityError:

1. Uvicorn loguea el error como "Exception in ASGI application"
2. El servidor entra en shutdown: "Waiting for connections to close"
3. Termina el proceso: "Finished server process [196052]"
4. Al reiniciar, el puerto 8000 sigue ocupado: "address already in use"

**No hay mecanismo de auto-restart.** El servidor no tiene supervisión (systemd, pm2, etc.) que lo reinicie automáticamente.

### 2.6 El frontend amplifica el daño

**Componente:** `web/src_ts/core/ui/RetryHandler.ts`

```typescript
scheduleRetry({ assistantEl, userText, reason, onRetry }: { ... }): void {
    this.count++;
    const delay = 2000 * this.count;  // 2s, 4s, 6s
    setTimeout(onRetry, delay);
}
```

**Flujo del reintento:**

1. `StreamOrchestrator.handleChatSend()` envía POST a `/chat/{session_id}`
2. Si el fetch falla (ERR_CONNECTION_REFUSED), el catch en `NDJSONStreamClient` emite un evento `error` de tipo `network`
3. `_handleStreamPostError()` en `StreamOrchestrator` decide si reintentar
4. `RetryController.shouldRetry()` retorna `true` (count < 3 && !hasContent)
5. `scheduleRetry()` espera 2s * count y llama `handleRetry()`
6. `handleRetry()` aborta el stream actual y llama `handleChatSend()` de nuevo
7. Se repite hasta `maxRetries = 3`

**Mientras tanto, los widgets pollean:**

| Widget/Componente | Endpoint | Frecuencia |
|---|---|---|
| HealthOverviewPanel | `/health` | ~2s |
| LanStatusPanel | `/api/node/sync/status` | ~5s |
| MemoryStatusPanel | `/api/memory/diagnostics` | ~8s |
| ModelAvailabilityPoller | `/models/availability` | ~30s |
| SSE stream | `/api/events/stream` | Persistente |

Todos estos requests fallan con `ERR_CONNECTION_REFUSED` y generan ruido en consola.

---

## 3. Flujo completo del request de chat

### 3.1 Ruta del request (backend)

```
Browser POST /chat/{session_id}?model=deepseek-v4-flash
    │
    ▼
FastAPI Router: web/routers/chat.py:82 → chat()
    │
    ├── rate_limit_middleware (app_factory.py:88)
    │   └── check_and_record(ip, max_requests) → 429 si excedido
    │
    ├── csp_middleware (app_factory.py:92)
    │   └── Agrega Content-Security-Policy header
    │
    ├── add_no_cache_headers (app_factory.py:105)
    │   └── Agrega no-cache para /static
    │
    ▼
chat() endpoint (chat.py:82-145):
    │
    ├── 1. repos = getattr(request.app.state, 'repos', None) or get_repos()
    │       └── Usa singleton inyectado en lifespan → NO crea conexiones nuevas
    │
    ├── 2. await repos.sessions.ensure(session_id, origin_node_id=...)  ← BUG AQUÍ
    │       └── SELECT → INSERT (TOCTOU)
    │
    ├── 3. history = await rebuild_history(session_id, model, messages_repo=repos.messages)
    │
    ├── 4. attachments = _save_attachments(session_id, files)
    │
    ├── 5. generate = build_stream_generator(...)
    │       └── Retorna generator async para StreamingResponse
    │
    └── 6. return StreamingResponse(generate(), media_type="application/x-ndjson")
```

### 3.2 Ruta del stream (backend)

```
StreamingResponse → generate() (chat_stream.py:55-181):
    │
    ├── async for tipo, token in _chat_stream(message, history, model, deps=orch_deps):
    │       └── Orchestrator ejecuta LLM + tools en loop
    │
    ├── yield serialize_stream_event(tipo, token) → NDJSON al cliente
    │
    ├── Si loop detectado → StreamRetryHandler.attempt_recovery()
    │
    ├── Si error → classify_error() → yield error event
    │
    └── finally:
        └── background_tasks.add_task(_vectorize_session, session_id, deps)
```

### 3.3 Ruta del request (frontend)

```
StreamOrchestrator.handleChatSend(text, files, model)
    │
    ├── Guard: _streamGuard, _lastStartMs (500ms cooldown)
    │
    ├── sessionStore.createSession() si no hay activeSessionId
    │
    ├── messageView.appendMessage(userMsg)
    │
    ├── NDJSONStreamClient.startStream(params)
    │       │
    │       ├── apiClient.chatStream(sessionId, message, model, controller)
    │       │       └── fetch(POST /chat/{sessionId}?model=...)
    │       │
    │       ├── if fetch fails → dispatcher.emit('error', {type:'network'})
    │       │
    │       └── if resp.ok → read NDJSON stream line by line
    │               └── parseStreamEvent(line) → dispatcher.emit(t, d, ctx)
    │
    └── _handleStreamCompletion(ctx, assistantEl, streamError)
            │
            ├── if streamError → _handleStreamPostError()
            │       └── RetryController.scheduleRetry() → handleRetry() → handleChatSend()
            │
            └── if hasContent → _handleSuccessfulStream()
```

### 3.4 Flujo del retry (frontend)

```
Error de red (ERR_CONNECTION_REFUSED)
    │
    ▼
NDJSONStreamClient.executeStream() catch block
    └── dispatcher.emit('error', {type:'network', message:'Connection failed'})
            │
            ▼
StreamOrchestrator dispatcher.on('error')
    └── streamError = {type:'network', message:'Connection failed'}
            │
            ▼
_handleStreamCompletion() → streamError is not null
    └── _handleStreamPostError({type:'network', message:'...'})
            │
            ▼
RetryController.shouldRetry(false) → true (count=0 < maxRetries=3, !hasContent)
    │
    ▼
RetryController.scheduleRetry({onRetry: () => handleRetry(text, model)})
    │
    ├── count++ (0→1)
    ├── delay = 2000 * 1 = 2000ms
    ├── setTimeout(onRetry, 2000)
    │
    ▼ (después de 2s)
handleRetry(text, model)
    ├── abort() ← limpia estado actual
    ├── _isRetry = true
    └── handleChatSend(text, undefined, model) ← reintenta
            │
            └── (si falla de nuevo → cycle se repite con delay 4s, 6s)
```

---

## 4. Arquitectura del sistema afectada

### 4.1 Connection Pool

**Archivo:** `src/memory/connection_pool.py`

```python
class ConnectionPool:
    async def acquire(self, db_path: str) -> Any | None:
        async with self._lock:
            pool = self._connections.get(db_path)
            if pool:
                return pool.pop()
            return None

    async def release(self, db_path: str, conn: Any) -> None:
        async with self._lock:
            # ...
```

- Pool máximo: 5 conexiones por DB
- Lock `asyncio.Lock()` protege el pool
- Las conexiones se reusan entre requests

**Relación con el bug:** El pool NO protege contra la race condition porque la operación SELECT+INSERT ocurre *después* de acquire, dentro del handler. Dos requests pueden adquirir conexiones diferentes y ejecutar SELECT+INSERT en paralelo.

### 4.2 Transaction Manager

**Archivo:** `src/memory/repos/base.py`

```python
@asynccontextmanager
async def _transaction(self):
    conn = await self._get_conn()
    engine = self._engine or get_engine()
    try:
        yield conn
        if engine is not None:
            await engine.commit(conn)
        else:
            await conn.commit()
    except Exception:
        if engine is not None:
            await engine.rollback(conn)
        else:
            await conn.rollback()
        logger.exception("Database transaction failed")
        raise
    finally:
        if self._conn is None:
            await conn.close()
```

**Relación con el bug:** El `_transaction()` hace rollback correctamente cuando el `IntegrityError` se propaga. Pero el `raise` en línea 48 re-lanza la excepción, que sube hasta uvicorn. El rollback previene corrupción de datos, pero no previene el crash del handler.

### 4.3 Repositories (Singleton vs Fallback)

**Archivo:** `src/memory/repos/__init__.py`

```python
def get_repos(conn=None) -> Repositories:
    repos = Repositories(
        messages=MessageRepository(conn=conn),
        sessions=SessionRepository(conn=conn),
        # ... todos los repos
    )
    return repos
```

**En chat.py:**
```python
repos = getattr(request.app.state, 'repos', None) or get_repos()
```

- `request.app.state.repos` es el singleton inyectado en `lifespan()`
- `get_repos()` es fallback que crea instancias nuevas
- En el crash, se usa el singleton (correcto)

---

## 5. Validación experimental

### 5.1 Reproducción del race condition

Se ejecutó un test con 10 workers concurrentes intentando insertar el mismo `session_id`:

```python
# Test: 10 workers concurrentes, SELECT + INSERT sin protección
async def ensure_session(worker_id):
    conn = await aiosqlite.connect(db_path)
    cursor = await conn.execute("SELECT 1 ...", (session_id,))
    row = await cursor.fetchone()
    if not row:
        await asyncio.sleep(0.001)  # Widens race window
        await conn.execute("INSERT INTO sessions ...", (session_id,))
        await conn.commit()

tasks = [ensure_session(i) for i in range(10)]
await asyncio.gather(*tasks)
```

**Resultado:**
```
Worker 8: INSERT succeeded
Worker 1: IntegrityError - UNIQUE constraint failed
Worker 4: IntegrityError - UNIQUE constraint failed
Worker 9: IntegrityError - UNIQUE constraint failed
Worker 5: IntegrityError - UNIQUE constraint failed
Worker 6: IntegrityError - UNIQUE constraint failed
Worker 7: IntegrityError - UNIQUE constraint failed
Worker 0: IntegrityError - UNIQUE constraint failed
Worker 3: IntegrityError - UNIQUE constraint failed
Worker 2: IntegrityError - UNIQUE constraint failed

Total errors: 9
RACE CONDITION REPRODUCED: True
```

### 5.2 Validación del fix

```python
# Fix: INSERT OR IGNORE (atómico)
async def ensure_session_fixed(worker_id):
    conn = await aiosqlite.connect(db_path)
    await conn.execute(
        "INSERT OR IGNORE INTO sessions ...",
        (session_id,)
    )
    await conn.commit()
```

**Resultado:**
```
Worker 0: INSERT OR IGNORE succeeded
Worker 8: INSERT OR IGNORE succeeded
... (todos los 10 workers exitosos)

Total errors: 0
Final row count: 1 (correcto)
FIX WORKS: True
```

---

## 6. Análisis de patrones TOCTOU similares en el codebase

Se realizó un barrido completo de SELECT+acción en todo el proyecto. Se encontraron **19 patrones** con diferentes niveles de severidad:

### 6.1 Tabla resumen

| # | Archivo | Líneas | Patrón | Transacción | Severity |
|---|---------|--------|--------|-------------|----------|
| 1 | `repos_memory/work_catalog_repo.py` | 260-328 | UPDATE then INSERT (upsert manual) | Implícita | MEDIUM |
| 2 | `repos/session_repository.py` | 65-79 | SELECT then INSERT | `_transaction()` | **BUG ACTUAL** |
| 3 | `repos/saved_widget_repository.py` | 13-37 | INSERT then SELECT then INSERT | `_transaction()` | LOW |
| 4 | `tools/save_memory.py` | 263-276 | SELECT get then DELETE | NO | LOW |
| 5 | `memory/vectorize_sessions.py` | 200-260 | SELECT dedup then INSERT | NO (fuera del lock) | MEDIUM |
| 6 | `memory/vectorize_sessions.py` | 470-547 | SELECT dedup then INSERT | NO (fuera del lock) | MEDIUM |
| 7 | `memory/curator/curate.py` | 265-305 | SELECT is_processed then LLM call then mark | NO | **HIGH** |
| 8 | `memory/curator/curate.py` | 362-403 | SELECT is_processed then LLM call then mark | NO | **HIGH** |
| 9 | `memory/curator/curate.py` | 408-486 | SELECT then INSERT+DELETE cross-DB | NO | MEDIUM |
| 10 | `memory/curator/gardener.py` | 108-151 | SELECT then DELETE | Implícita | LOW |
| 11 | `memory/curator/gardener.py` | 154-216 | SELECT then DELETE+UPDATE | Implícita | LOW |
| 12 | `memory/curator/gardener.py` | 344-407 | SELECT then UPDATE/DELETE | commit por par | LOW |
| 13 | `repos_memory/deleted_session_repo.py` | 120-146 | SELECT then DELETE then INSERT | Implícita | LOW |
| 14 | `repos_memory/deleted_session_repo.py` | 261-285 | SELECT then DELETE | Implícita | LOW |
| 15 | `memory/vector/store.py` | 245-320 | SELECT then UPDATE (query_count) | Lock + commit | LOW |
| 16 | `memory/vector/store.py` | 351-370 | SELECT then DELETE | Lock + commit | LOW |
| 17 | `tools/save_memory.py` | 430-459 | SELECT then UPDATE (hash) | Implícita | LOW |
| 18 | `web/routers/node_memory.py` | 75-95 | SELECT dedup then INSERT | NO | MEDIUM |
| 19 | `memory/memory_schema.py` | 274-344 | SELECT then UPDATE+DELETE (dedup migration) | Implícita | LOW |

### 6.2 Detalle de los más críticos

#### Finding 7 & 8: `curate.py` — SELECT is_processed + LLM + mark (HIGH)

```python
# curate.py:265-289
if not catalog.is_processed(source_key):   # SELECT
    result = await llm_curate(content)      # LLM call (segundos a minutos)
    catalog.mark(source_key)                # INSERT/UPDATE
```

**Problema:** Dos runs concurrentes del curador ambos ven "not processed", ambos hacen llamadas LLM costosas, ambos marcan como procesado. El segundo sobreescribe el primero. Desperdicio de tokens y tiempo.

**Fix:** Usar `INSERT ... ON CONFLICT DO UPDATE` directamente, o un advisory lock/row.

#### Finding 5 & 6: `vectorize_sessions.py` — Dedup SELECT fuera del lock (MEDIUM)

```python
# vectorize_sessions.py:200-244
cursor = await conn.execute("SELECT rowid FROM vec_meta WHERE content_hash = ?", (h,))
if not await cursor.fetchone():
    # ... generate embedding ...
    store.insert(...)  # <-- store.insert() tiene su propio lock
```

**Problema:** El SELECT dedup está fuera del `VectorStore._lock`. Dos concurrentes pueden ver "no existe" y ambos insertar.

**Fix:** Mover el dedup check dentro del VectorStore bajo su lock, o usar `INSERT OR IGNORE` y verificar `rowcount`.

#### Finding 18: `node_memory.py` — HTTP endpoint dedup fuera del lock (MEDIUM)

```python
# node_memory.py:75-95
cursor = await conn.execute("SELECT rowid FROM vec_meta WHERE content_hash = ? LIMIT 1", (h,))
if not await cursor.fetchone():
    store.insert(...)  # <-- store tiene lock, SELECT no
```

**Problema:** Mismo patrón que Finding 5/6 pero expuesto vía HTTP.

#### Finding 1: `work_catalog_repo.py` — Upsert manual (MEDIUM)

```python
# work_catalog_repo.py:260-328
cursor = await conn.execute("UPDATE work_catalog SET ... WHERE id = ?", ...)
if cursor.rowcount == 0:
    await conn.execute("INSERT INTO work_catalog ...")  # ← IntegrityError si PK duplicada
```

**Fix:** Usar `INSERT ... ON CONFLICT(id) DO UPDATE SET ...`

---

## 7. Causa del shutdown del servidor

### 7.1 ¿Por qué muere el servidor?

El `IntegrityError` es una excepción Python normal. FastAPI/Starlette debería manejarla y retornar un 500. Sin embargo, el log muestra:

```
ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)
```

Esto indica que Starlette está usando `anyio.TaskGroup` internamente (nuevo en versiones recientes de Starlette/anyio). Cuando una excepción se escapa de un `TaskGroup`, se envuelve en un `ExceptionGroup`. Dependiendo de la configuración de manejo de excepciones, esto puede causar que el servidor se cierre en lugar de simplemente retornar un 500.

**En Starlette ≥0.38 / anyio ≥4.x**, las `ExceptionGroup` se propagan de forma diferente. Si el middleware stack no las maneja correctamente, pueden causar el cierre del servidor.

### 7.2 ¿Por qué no se recupera?

No hay mecanismo de auto-restart configurado. El servidor necesita:
- Un supervisor (systemd, pm2, supervisord)
- O un wrapper que reinicie en caso de crash
- O manejo adecuado de la excepción en el handler

---

## 8. Impacto del crash en el frontend

### 8.1 Cascada de errores

```
Server muere
    │
    ├── POST /chat/{session_id} → ERR_CONNECTION_REFUSED
    │       └── RetryController: scheduleRetry(2s)
    │               └── POST /chat/{session_id} → ERR_CONNECTION_REFUSED (otra vez)
    │                       └── RetryController: scheduleRetry(4s)
    │                               └── POST /chat/{session_id} → ERR_CONNECTION_REFUSED
    │                                       └── maxRetries alcanzado → error card
    │
    ├── GET /health → ERR_CONNECTION_REFUSED (cada ~2s)
    ├── GET /api/node/sync/status → ERR_CONNECTION_REFUSED (cada ~5s)
    ├── GET /api/memory/diagnostics → ERR_CONNECTION_REFUSED (cada ~8s)
    ├── GET /models/availability → ERR_CONNECTION_REFUSED (cada ~30s)
    ├── GET /api/events/stream → ERR_CONNECTION_REFUSED (SSE reconnect loop)
    └── POST /api/logs/client → ERR_CONNECTION_REFUSED
```

### 8.2 El loop de SSE

El `EventSource` del navegador intenta reconectar automáticamente al SSE stream. Cada intento fallido genera un error en consola. El browser tiene un mecanismo de backoff exponencial para EventSource, pero los logs muestran muchos intentos fallidos antes de que se detenga.

---

## 9. Fixes propuestos (priorizados)

### 9.1 Fix inmediato (session_repository.py)

**Opción A — INSERT OR IGNORE (recomendado):**

```python
async def ensure(self, session_id: str, *, origin_node_id: str = "") -> None:
    async with self._transaction() as conn:
        try:
            await conn.execute(
                "INSERT OR IGNORE INTO sessions "
                "(session_id, name, created_at, origin_node_id) "
                "VALUES (?, '', ?, ?)",
                (session_id, datetime.now().isoformat(), origin_node_id)
            )
        except sqlite3.OperationalError:
            # Pre-migration-025 DB: origin_node_id column missing
            await conn.execute(
                "INSERT OR IGNORE INTO sessions "
                "(session_id, name, created_at) "
                "VALUES (?, '', ?)",
                (session_id, datetime.now().isoformat())
            )
```

**Opción B — Catch IntegrityError:**

```python
try:
    await conn.execute(
        "INSERT INTO sessions ...",
        (session_id, datetime.now().isoformat(), origin_node_id)
    )
except sqlite3.IntegrityError:
    pass  # Ya existe, race condition controlada
except sqlite3.OperationalError:
    # Fallback pre-migration
    ...
```

### 9.2 Fix para otros patrones TOCTOU (prioridad media)

| Finding | Fix | Esfuerzo |
|---------|-----|----------|
| #1 (work_catalog_repo) | `INSERT ... ON CONFLICT DO UPDATE` | Bajo |
| #5, #6 (vectorize_sessions) | Mover dedup dentro del lock o `INSERT OR IGNORE` | Medio |
| #7, #8 (curate.py) | Advisory lock o `INSERT ... ON CONFLICT DO NOTHING` | Medio |
| #18 (node_memory.py) | Mover dedup dentro del VectorStore lock | Bajo |

### 9.3 Fix para resiliencia del servidor

1. **Agregar auto-restart:** Usar systemd, pm2, o un wrapper script
2. **Mejorar exception handlers:** Asegurar que `ExceptionGroup` de Starlette se maneje correctamente
3. **Graceful shutdown:** Manejar `SIGTERM` y limpiar conexiones antes de cerrar

---

## 10. Checklist de verificación

- [ ] Aplicar fix `INSERT OR IGNORE` en `session_repository.py:ensure()`
- [ ] Verificar que el fix no rompe la lógica de `origin_node_id` (migration 025)
- [ ] Ejecutar tests existentes con `pytest --testmon`
- [ ] Buscar y corregir otros patrones TOCTOU en la tabla de la sección 6
- [ ] Investigar el `RuntimeWarning: coroutine 'run' was never awaited` como bug separado
- [ ] Configurar auto-restart para el servidor
- [ ] Verificar que el frontend maneja correctamente la caída del servidor (ya lo hace con RetryController)
