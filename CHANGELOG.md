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

---

## [2026-06-16] — Sistema Lego de estilos + Backend Composition Root

### 🧱 Frontend: Sistema de Layout Lego (5 nuevos bloques)

- **`ILayoutGrid` / `GridController`** — motor de grid dinámico: celdas reordenables, persistencia en localStorage, CSS Grid nativo
- **`ICanvasOverlay` / `CanvasOverlay`** — canvas full-page con 4 efectos (rain, snow, particles, fireworks) + drawing mode para que el usuario dibuje bloques y la IA los interprete
- **`ICSSInjector` / `CSSInjector`** — `injectCSS(id, css)` y `removeCSS(id)` para estilos dinámicos sin tocar archivos
- **`IAudioBus` / `AudioBus`** — sonidos automáticos en eventos del chat (message, error, notification, send)
- **Layout types** (`types/layout.ts`) — interfaces centralizadas para todo el sistema de estilos

### 🧱 Frontend: Refactor Canvas (F → A en desacople)

- `ICanvasCardManager` + `ILayoutStore` interfaces creadas
- `CanvasCardManager` ahora implementa `ICanvasCardManager`
- `CanvasLayoutStore` implementa `ILayoutStore`
- `CanvasWorkspace` recibe `cardManager` y `layoutStore` por constructor (eliminados 2 `new` internos)
- Event listeners de toggle/close/gutter ahora se limpian en `reset()`
- Último `: any` del módulo eliminado (reemplazado por `unknown`)
- DOM containers se asignan via `setContainer()` post-constructor

### 🧱 Frontend: Preparación para IA real

- `ToolCallPayload` tipado como el backend (agregados `partial`, `idx`, `args`)
- `_stream_args` y `partial` ignorados (como JS production)
- Heartbeats resetear timeout vía `onChunk`
- Soporte `files` en NDJSONStreamClient
- First token limpia "✍️ Pensando..."
- Sidebar refresh + pills error en fallo terminal
- `lastAssistantMsgEl = null` en cleanup (memory leak cerrado)

### 🧱 Frontend: Optimizaciones

- `manualChunks` en vite: widgets, streaming, rendering, debug separados → app_mock.js **118KB → 30KB**
- `sourcemap` condicional solo en dev → -648KB en prod
- `handleContent()` incremental — salta 6/8 pasos DOM en tokens sin widgets
- RAF throttle en drag handler de CanvasCardManager
- 96/96 tests, tsc OK, build OK

### 🔧 Backend: Composition Root + DI (Fases 1-4)

- **`IEventBus` Protocol** en `event_bus.py` — EventBus implementa interfaz, inyectable
- **`set_event_bus()`** — composición root inyecta instancia, `get_event_bus()` la prefiere
- **Composition Root** en `app_factory.py` — crea EventBus + Repositories en `app.state`
- **Protocols exportados** desde `src.api.orchestrator` (HistoryServiceProtocol, etc.)
- **`chat_stream.py`** parametrizado — acepta `orchestrator_deps` opcional
- **Routers limpios** — usan `request.app.state.*` con fallback a singletons

### 🔧 Backend: SessionStore conectado a API real

- SessionStore eliminó datos mock — ahora carga sesiones desde `GET /sessions`
- `ApiClient`: nuevos métodos `getSessions()`, `createSession()`, `getSessionMessages()`
- `POST /sessions/create` + `GET /sessions` endpoints JSON agregados
- Delete sesión persiste en backend + recarga desde API

### 🐛 Bugs corregidos

- Widgets no se renderizaban por regex incorrecta en ContentHandler
- `: any` → `: unknown` en type guard de LayoutStore
- `setInterval` debug panel sin cleanup
- `widgetObserver.disconnect()` faltante en reset
- EventBus self-reference (TypedEventBus vs EventBus)
- Tests de debug router adaptados a nuevos parámetros
- Panel derecho visible por CSS Grid sin `minmax`
- Audio 404 silenciado en AudioBus
- Client logs 422 silenciado en Logger

### 📦 Build

- `app_mock.js`: **37 KB** (con code splitting)
- `app.js` (JS prod): **70 KB**
- Chunks: widgets (20 KB), streaming (52 KB), rendering (22 KB), debug (6 KB)
- Total TS: **39 clases, 39 interfaces** — 100% Lego
- TS Lines: **7,762** (sin tests)

### 🧪 Tests

- Backend: 67/68 tests pasan (1 pre-existing frozenset)
- Frontend TS: 96/96 tests
- Frontend JS: sin cambios
