# Changelog ??? K-Chat

## [2026-06-18] - Lifecycle unificado + Singleton x Testing + Frontend Widget Runtime

### 🔥 Bugs críticos corregidos

- **Corrutinas sin consumir en LLM failover** (`failover.py`): `_mark_and_refresh()` llamaba a `discovery.get_verified_models()` (un `async def`) desde contexto sync sin await — la corrutina se descartaba y el refresh de modelos verificados NUNCA ocurría. Ahora se consume via `loop.create_task()` o `asyncio.run()`.
- **Corrutina sin consumir en discovery** (`discovery.py`): `loop.create_task()` en `_ping_free_model_availability()` se llamaba sin verificar si había un event loop corriendo. Ahora con `try/except RuntimeError` guard.
- **ModelState retornaba modelo fallido como "last resort"**: `switch_model()` devolvía un modelo ya fallido si todos los candidatos habían fallado, causando loops infinitos de failover. Ahora levanta `RuntimeError` limpio.
- **SECONDARY_MODEL vacío**: `SECONDARY_MODEL = ""` inhabilitaba el failover a modelo secundario. Ahora es `"big-pickle"`.
- **Rate limiter como global module-level**: compartido entre tests y requests, causando contaminación de estado en tests concurrentes. Movido a `app.state`.
- **Gateway sin reset de estado**: `main()` no limpiaba `_services`, `_shutdown` entre ejecuciones. Ahora `reset_gateway_state()` al inicio.
- **Placeholder k0-k19 en MEMORY.md**: 21 entradas basura del curador eliminadas.

### 🧠 Singleton Elimination (18 módulos con `configure_*`/`reset_*`)

Todos los módulos con estado module-level ahora exponen un par `configure_*`/`reset_*` para inyección explícita + `get_*` con prioridad: (1) instancia explícita, (2) DI container, (3) lazy singleton fallback.

| Capa | Módulo | Funciones |
|------|--------|-----------|
| **LLM** | `circuit_breaker.py` | `configure_breaker()` / `reset_breaker()` |
| **LLM** | `container.py` | `configure_container()` / `reset_container()` |
| **LLM** | `model_registry.py` | `configure_model_registry()` / `reset_model_registry()` |
| **LLM** | `model_state.py` | `configure_state()` / `reset_state()` |
| **LLM** | `providers.py` | `configure_registry()` / `reset_registry()` |
| **LLM** | `rate_limit_state.py` | `configure_rate_limit_store()` / `reset_rate_limit_store()` |
| **Memory** | `connection_pool.py` | `configure_connection_pool()` / `reset_connection_pool()` |
| **Memory** | `memory_pool.py` | `configure_memory_pool()` / `reset_memory_pool()` |
| **Memory** | `engine_state.py` | `configure_engine()` / `reset_engine()` |
| **Memory** | `embeddings/service.py` | `configure_model()` / `reset_model()` |
| **Memory** | `keywords/extractor.py` | `configure_global_extractor()` / `reset_global_extractor()` |
| **Memory** | `retrieval/reranker.py` | `configure_reranker()` / `reset_reranker()` |
| **Infra** | `logbus/__init__.py` | `configure_logbus()` / `reset_logbus()` |
| **Infra** | `config_loader.py` | `reset_dotenv_state()` |
| **Web** | `services/file_logger.py` | `configure_log_dirs()` / `reset_log_dirs()` |
| **Web** | `services/event_bus.py` | `reset_event_bus()` |
| **Web** | `services/model_catalog.py` | `reset_model_cache()` |
| **Entry** | `gateway.py` | `reset_gateway_state()` |

Todos reseteables desde un solo punto: **`src/api/lifecycle.reset_runtime_state()`** que orquesta los 18 módulos.

### 🏗️ DI Composition Root extendido

- **SkillRegistry** ahora vive en `app.state` en lugar de module-level — los routers lo resuelven vía `request.app.state.skill_registry`.
- **Rate limiter** movido de `_rate_limit_store = RateLimitStore()` global a `app.state.http_rate_limit_store`.
- **`ToolRegistry.reset()`** y **`SkillRegistry.reset()`** añadidos — permiten rediscovery y test isolation.
- **Log dirs dinámicos**: `web/routers/logs.py` ya no importa `SERVER_LOG_DIR`/`CLIENT_LOG_DIR` en módulo — llama a `get_server_log_dir()`/`get_client_log_dir()` en cada request.
- **Provider injectable**: `api_call._resolve_provider()` y `_api_call()` aceptan `provider_fn: Any | None` — la vieja singleton `_get_provider()` quedó como wrapper compatible.

### 🐍 LLM Layer: Async Safety + Código limpio

- **`anyio.fail_after`** reemplaza `asyncio.wait_for` en `client.py` — mejor manejo de cancelación.
- **`_await_if_needed()`**: helper que detecta corrutinas y las await automáticamente — protege contra sync/async mismatches.
- **`_mark_model_success()`**: extraído 3 instancias de `mark_available` + `record_success` en `client.py`.
- **`_resolve_config()`**: patrón "if config is None: load_config()" extraído de múltiples funciones en `discovery.py`.
- **`_model_id()`**: extraído del patrón `model if isinstance(model, str) else getattr(model, "id", "")` (~6 usos).
- **`_make_zen_provider()`**: construcción de Zen provider (~15 líneas) extraída de 3 ubicaciones en `discovery.py`.
- **Selector con DI**: `_get_free_models_sync()` y `_get_default_model_candidates()` aceptan `free_models_fn`/`verified_models_fn` opcionales.
- **`create_provider()`** simplificado: base URL como one-liner ternario, registry simplificado.
- **ModelState.PRIORITY** filtra falsy: `[m for m in priority if m]` — evita modelos vacíos.

### 🔧 Memory Layer: Upward coupling eliminado

- **`src/memory/curator/curate.py`**: `_default_save_memory` (que importaba `src.tools.save_memory`) reemplazado por `_noop_save_memory`. Entry points (`.kairos/curator.py`, `.kairos/memory_backup.py`) inyectan `save_memory_fn`.
- **`src/memory/operations/archive.py`**: `_archive()` ahora requiere `save_memory_fn: Callable` — ya no importa internamente. `manage_memory.py` lo inyecta vía lambda.
- **Reranker**: 6 nuevos tests unitarios cubren `load_model` (éxito/fallo), fallback, empty candidates, sorting, error propagation, y unload.
- **Embedding service**: `configure_model()`/`reset_model()` permiten inyectar modelo dummy sin red.

### 🌐 Web Layer: Widget detection runtime + build CI

- **Nuevo sistema frontend de widgets**: `stream-dispatcher.js` (pub/sub), `contract.js` (constantes), `state-manager.js` (estado en Map), `widget-detector.js` (scanner de bloques ` ```html-widget` y `[Widget:]` en streaming).
- **CI refactorizado**: `npm install` → `npm ci`, se agregó `npm run build`, `npm run test:ts` + `npm run test:js`. Python tests reemplazados por smoke tests específicos (3 archivos).
- **Docker**: `CMD` cambiado de uvicorn directo a `python -m src.gateway` (multi-service launcher). Removido `config.py` del build.
- **Lifespan**: shutdown ahora llama a `reset_runtime_state()`, `reset_config_cache()`, `reset_event_bus()`, y `logbus.stop()` en el orden correcto.

### 📦 Dependencias

- **Agregado**: `anyio>=4.0.0,<5.0.0` (timeout handling robusto)
- **Removidos**: `sentence-transformers` (reemplazado por fastembed), `hf_xet`, `huggingface-hub[hf_xet]`, `pytest-mock`, `trio`

### 🧪 Tests (24 nuevos, ~40 modificados)

- **8 tests singleton**: `test_circuit_breaker`, `test_container`, `test_rate_limit_state`, `test_model_registry_singleton`, `test_connection_pool`, `test_context_runtime_reset`, `test_gateway_state` — verifican `configure_*`/`reset_*` con finally cleanup.
- **8 tests memory**: `test_connection_pool`, `test_embedding_service`, `test_engine_state`, `test_keyword_extractor`, `test_memory_pool`, `test_reranker`, `test_retrieval_service`, `test_vectorize_sessions`.
- **4 tests web**: `test_app_factory_config`, `test_file_logger_reset`, `test_logbus`, `test_tool_registry_reset`.
- **Test isolation**: `reset_shared_runtime_state` fixture (autouse=True) en `conftest.py` — limpia 18 singletons antes/después de cada test.
- **Schema inline**: `conftest.py` ya no importa `src.memory.schema.init_db()` — define DDL propio para 10 tablas + 9 índices.
- **`test_app_factory.py`**: `_mock_startup` fixture mockea 6 dependencias; `TestClient` envuelto en `with` context manager.
- **`test_orchestrator.py`**: mocks envueltos en `RetrievalService(config=cfg, retrieval_service=mock)` real en lugar de mock directo.
- **`test_anti_regression.py`**: 9 tests legacy JS eliminados, 8 renombrados a TS, 10 nuevos tests TS.
- **`test_llm.py` y `test_models.py`**: nuevos patrones DI via `provider_fn` en lugar de `_get_provider()` mock.
- **`pytest.ini`**: filtro `DeprecationWarning` para `aifc` (eliminado en Python 3.13).

### 📚 Documentación actualizada

- **`docs/MODULES.md`**: 10+ módulos nuevos documentados, campos `reset_*` agregados a módulos existentes.
- **`docs/HEALTH.md`**: sección DIP expandida con ~20 módulos lifecycle-controlados; DB pool re-caracterizado de "no pool" a "process-local pools".
- **`docs/llm_architecture.md`**: diagrama de `create_provider()` actualizado; 3 ítems de "lo que podría mejorar" eliminados.
- **`MEMORY.md`**: 21 placeholders del curador eliminados.

### Integración

- HEAD en `1d33756` (v0.0.63)
- 56 archivos modificados, 24 nuevos
- +1089 líneas, −590 líneas

---

### Multi-Device SSE
- **`KAIROS_WEB_URL` ahora acepta múltiples URLs separadas por coma**: el bot de Telegram notifica a TODOS los web UIs simultáneamente.
  - `adapter.py`: `_get_sse_notify_url()` reemplazado por `_get_sse_notify_urls()` que devuelve lista.
  - Nuevo helper `_notify_all()` — POSTea el evento a todas las URLs configuradas.
  - `ws_client.py`: el fallback HTTP de `send_event()` también usa `_notify_all()`.
  - Cada fallo individual se loggea sin bloquear a los demás.
  - Uso: `KAIROS_WEB_URL="http://127.0.0.1:8000,http://192.168.1.100:8000"é

### Accesibilidad
- `<select id="model-select">` ahora tiene `aria-label="Seleccionar modelo de lenguaje"é (DevTools AI audit).
- Polling de `/models/availability` reducido de 30s a 60s (success) / 120s (error). El endpoint es puramente en memoria, no consume tokens.

### Fixes de tests post-refactor
- `conftest.py`: columna `auto_memories` agregada al schema de `debug_info`.
- `test_web_server.py`: `request: Request` y `BackgroundTasks` pasados correctamente a routers con DI.
- `test_db_query.py`: todas las llamadas a `db_query.run()` ahora tienen `await`.
- `test_history_service.py`: asserts actualizados con `memory_results=None`.

---

## [2026-06-17] - Estabilizacion local + logs al gateway

### Bugfixes
- Sidebar desincronizado: el contador ahora muestra el total real de mensajes y no un valor cacheado o parcial.
- Rename de sesiones: el flujo de rename en `chat-ts` y en el frontend clasico ahora persiste y refresca la vista.
- Assets 404: `skills-ui.js` vuelve a servir correctamente y se elimina el error de carga dinamica.
- Logs al gateway: eventos clave de sesion ahora se registran en `gateway_log` (`session_created`, `session_renamed`, `session_deleted`).

### Arquitectura
- Se eliminaron imports directos innecesarios a `src.memory` desde la capa web y desde `gateway`.
- El arranque y shutdown de modelos quedaron desacoplados con importacion dinamica.
- `buildIframeSrc` mantiene el codigo del widget sin transformarlo, alineado con el contrato de tests.

### Dependencias
- Se ampliaron los requisitos de instalacion para incluir dependencias de ASR, embeddings y tests.

### Verificacion
- `tests/unit/test_anti_regression.py` ahora pasa.
- `tests/unit/test_pages_router.py` y `tests/unit/api/test_api_session.py` pasan.
- `GET /health` responde OK despues del reinicio del server.

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
