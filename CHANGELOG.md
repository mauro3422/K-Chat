# Changelog — K-Chat

## [2026-06-16] — Auditoría general + estabilización full-stack

### 🔥 Bugs críticos corregidos
- **Connection leak**: `_BaseRepository._transaction()` ahora cierra conexiones en `finally` (antes se filtraban)
- **Dual-write no atómico** (bug #11): save_memory ahora escribe a `.tmp` + `os.replace()` atómico, con restore on failure
- **entity_search case-sensitive** (bug #2): queries usan `LOWER()` en ambos lados del WHERE
- **Hardcode paths**: curator, gardener, tracer ahora resuelven paths dinámicamente
- **Cache invalidation prematura** (bug #4): solo invalida tras write exitoso

### 🧠 Memoria (12+ fixes)
- **Connection pool**: `threading.Lock` → `asyncio.Lock`, sync/async consistency fix
- **Thread-safety**: keywords extractor, entity extractor, reranker singleton — locks agregados
- **Async flushes**: clustering (heuristic.py, relations.py) y entity linker migrados de `sqlite3` sync a `aiosqlite`
- **Env vars unificadas**: `K_CHAT_MEMORY_DB` → `resolve_memory_db_path()` en garderner/tracer
- **Dead code eliminado**: `classify_exchange`, `extract_keywords_batch`, `extract_entities_batch`, `cosine_similarity_keywords`, `backfill_relevance.py`, `entity_search_batch`
- **Split manage_memory.py**: 683→140 líneas, 7 archivos en `src/memory/operations/`
- **Split hybrid_retriever.py**: 304→206 líneas, hydrator + tracker extraídos
- **Hash dedup normalizado**: whitespace + lowercase antes de hashear

### ⚡ Frontend performance (8 fixes)
- **SSE incremental rendering**: `insertAdjacentHTML('beforeend')` con tracking de `dataset.renderedLen` — fin del innerHTML spam
- **CSS optimizado**: box-shadow reemplazado por outline+opacity (solo composite layer, sin repaints)
- **Logger production guard**: console mirror solo en localhost/DEBUG
- **Event listener cleanup**: `dispose()` en NotificationBell, SessionStore, CanvasWorkspace
- **EventBus limit**: MAX_LISTENERS=50 con warning de leak
- **Virtual scrolling**: IntersectionObserver windowing — mensajes fuera de viewport se reemplazan con placeholder
- **Widget/Iframe GC**: `destroyContainer()` + MAX_WIDGETS=10
- **Vendor bundling**: marked + dompurify via npm en vez de scripts externos

### 🏗️ Infraestructura (12+ fixes)
- **LogBus**: sistema unificado de logging async con queue, consumer batch, writers JSONL+SQLite+Console, middleware FastAPI
- **LogBus API**: `GET /api/logbus`, `/tail`, `/sessions/{id}`, `/cleanup`
- **LogBus conectado**: gateway_log, chat_journal, telemetry_service wrappeados a LogBus
- **Docker**: multi-stage builder, non-root `kchat` user, python 3.13-slim, HEALTHCHECK
- **DBs huérfanas**: eliminadas 5 DBs de 0 bytes en raíz del proyecto
- **`.dockerignore`**: completado con logs/, memory/, data/, *.db
- **Deps pineadas**: aiosqlite, pytest-testmon con versiones fijas
- **`.env.example`**: completado con todas las claves soportadas
- **Ruff**: actualizado v0.4.4 → v0.11.2
- **Coverage**: pytest-cov configurado (opcional)

### 🎯 Core/LLM (8 fixes)
- **Orchestrator SRP**: auto-retrieval extraído a `RetrievalService` — orchestrator pierde ~50 líneas
- **load_config unificado**: patrón duplicado `if config is None: load_config()` eliminado de 6 archivos → `src/_config.resolve_config()`
- **load_dotenv lazy**: movido de import-time a llamada explícita en `load_config()`
- **Memory leak rate limiter**: `_call_counts` con cleanup de sesiones inactivas cada 100 calls
- **Circuit breaker**: `CircuitBreaker` con estados CLOSED/OPEN/HALF_OPEN, 3 fallos → 60s cooldown. Previene loop infinito de failover
- **Model consolidation**: `_verified_models` movido de model_state a model_registry
- **Retrieval throttle**: `dict[str,int]` reemplazado por `OrderedDict` con LRU eviction
- **Tests de retrieval**: 9 tests para fuse_rrf, fuse_weighted_sum, normalize_scores

### 🧪 Tests
- 9 tests nuevos para RRF fusion
- 3 tests de repositorios arreglados (telegram_chat_id column)
- Tests de discovery/llm adaptados a model_registry
- BackendLogHandler deprecado, test adaptado

---

## [2026-06-16] — Refactor masivo: desacople total, lifecycle, SSE, tests (Frontend TS)

### 🏗️ Arquitectura (Lego total)

- **4 interfaces nuevas**: `IDebugManager`, `IIframeBuilder`, `IWidgetContainerRenderer`, `IStreamDispatcher<T>` — todas las clases inyectables ahora tienen interfaz
- **IMessageView e IChatForm** creadas — sellan los últimos 2 puntos de acoplamiento concreto
- **StreamOrchestrator** extraído de `app_mock.ts` (369→256 líneas) — god object eliminado
- **ContentHandler** dividido en 4 archivos: `ReasoningHandler`, `ToolCallRenderer`, `ErrorRenderer`, `ContentHandler` (coordinador)
- **CanvasWorkspace** dividido en 3 clases: `CanvasWorkspace`, `CanvasCardManager`, `CanvasLayoutStore`
- **core/ reestructurado** en 6 subdirectorios: `debug/`, `infra/`, `notification/`, `session/`, `ui/`, `widget/`
- Re-exports en `core/*.ts` — 0 imports rotos

### 🛡️ Type safety

- `: any` reducido de **41 → 1** (type guard válido en CanvasLayoutStore)
- `as any` eliminado de **7 → 0** (iframe properties ahora usan `setAttribute`)
- `StreamDispatcher` ahora es genérico `<TContext>` con handlers tipados
- Catch clauses tipados como `unknown`

### 🚦 Stream lifecycle completo

- Stream guard: temporal (500ms anti-doble click) + booleano (anti-concurrente)
- Timeout 120s con reset RAF-debounced en cada chunk
- Auth/rate_limit = terminal sin retry; otros errores → retry con backoff 2s/4s/6s
- Respuesta vacía con reasoning/tool calls presente → no retry automático
- Respuesta vacía sin reasoning → retry hasta 3 intentos
- Error cards con botón reintentar y variante rate-limit

### 📡 Canales de comunicación

- **NDJSONStreamClient** (renombrado de SSEClient) — `POST /chat/{session_id}` con fetch + ReadableStream
- **SSEClient** (nuevo) — `EventSource /api/events/stream` para notificaciones cross-session
  - `stream:*` → renderiza en vivo via ContentHandler (Telegram tokens)
  - `new_message` → appendMessage o reloadMessages + unread marks
  - `session_deleted` / `message_deleted` → mutaciones vía EventBus
- **StreamSimulator** — modo dev sin backend, convive con el modo real

### 🐛 Bugs corregidos

- `ApiClient.sendClientLogs()` ahora envía el array directo (no envuelto en `{entries}`)
- `ApiClient.sidebar()` acepta `?current=<sessionId>` opcional
- `Widget code persistence` — `WidgetStateManager` persiste código al backend

### 🎛️ Features agregados

- **Model selector**: lee `#model-select`, guarda en localStorage, pasa `?model=` al backend
- **Unread marks**: sidebar marca sesiones con `.has-new` cuando llegan mensajes SSE de sesión no activa
- **RetryController**: port del JS `retry-handler.js` con 3 intentos máximo, backoff progresivo
- **StreamSimulator extendido**: 15 escenarios de error, detección de intención

### 🧪 Tests (96 tests, todos pasando)

- **`dom-contracts.test.ts`** (31) — verifica todos los CSS class constants
- **`message-view.test.ts`** (15) — beginStreaming, appendMessage, simple + phases
- **`reasoning-handler.test.ts`** (10) — DOM de razonamiento y memorias
- **`tool-call-renderer.test.ts`** (6) — pills, transiciones calling→ok→error
- **`error-renderer.test.ts`** (7) — error cards, rate limit, retry button
- **`stream-dispatcher.test.ts`** (7) — eventos on/off/emit/removeAll
- **`retry-controller.test.ts`** (11) — count, shouldRetry, schedule, timeout
- **`session-list.test.ts`** (9) — render, icons, acciones, unread marks

### 📦 Build

- `npx tsc --noEmit` — 0 errores
- `npm run build` — ~700ms, bundle ~45KB
- `npm run test:ts` — 96 tests, ~800ms

### Pendiente (no bloquea)

- ASR (voz) — 8 archivos JS, ~940 líneas
- Widget toolbar (editar/historial) — 4 archivos JS, ~290 líneas
- Conexión AI — solo reemplazar `StreamSimulator` por `NDJSONStreamClient.startStream()`
