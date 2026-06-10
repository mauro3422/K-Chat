# Changelog

Todas las versiones de Kairos.

## [v0.0.1] — 2026-06-08

### Agregado
- Chat funcional vía CLI (`src/cli.py`) y web (`web/server.py` + `web/routers/`)
- SQLite como motor de persistencia
- Sistema de herramientas (tools) con auto-descubrimiento via `importlib`
- Herramientas iniciales: `fetch_url`, `read_file`, `write_file`, `web_search`
- Arquitectura básica de capas: entry → core → llm/tools/memory/context
- Streaming básico de respuestas del LLM
- Sistema de sesiones con UUID
- Renderizado de mensajes con fases (razonamiento → herramientas → contenido)
- Configuración vía `.env` + variables de entorno

### Estructura inicial
- `src/`: CLI, core, LLM, tools, memory, context
- `web/`: FastAPI server, routers HTML, static assets
- `tests/`: Tests unitarios básicos

---

## [v0.0.2] — 2026-06-08

### Agregado
- **Arquitectura Lego**: módulos independientes que se ensamblan sin acoplamiento
- **Streaming real**: NDJSON como formato de serialización, SSE-like desde el backend
- **Fallback resiliente**: `_switch_model()` y `_mark_and_refresh()` para modelos caídos
- **Sistema de Widgets**: estado de widgets por sesión + widget DB oficial versionada
- **UI Dashboard**: sidebar de sesiones, vista de mensajes con fases colapsables
- **Herramienta `save_memory`**: persistencia de hitos y datos en memoria del sistema
- **Herramienta `read_skill`**: carga de skills desde el directorio `skills/`
- **Herramienta `save_widget` / `update_widget` / `get_widget_code`**: ciclo de vida de widgets
- **Compresor de historial**: compresión automática cuando > 40 mensajes o > 6k tokens
- **Auto-rename de sesiones**: rename automático vía LLM en segundo plano
- **CLI mejorado**: comandos `/model`, `/clear`, `/help`

### Corregido
- Manejo de errores en streaming (timeout, rate_limit, network, model, empty_response)
- Limpieza de historial al cambiar de modelo

---

## [v0.0.3] — 2026-06-08

### Agregado
- **API Facade** (`src/api.py`): single entry point con 15+ funciones públicas
- **Repository Pattern**: `_BaseRepository` + 6 repositorios tipados en `src/memory/repositories.py`
- **Thread safety**: `threading.Lock` en operaciones críticas de DB
- **Migraciones de esquema**: 9 migraciones idempotentes (001→009)
- **Pipeline de pruebas automatizado**: 233 tests (unitarios + integración)
- **Linting**: configuración ruff, pyright type checking
- **Módulo de paths**: `src/paths.py` con constantes centralizadas
- **Helper de widgets**: `src/tools/_widget_helpers.py` con sanitización + validación
- **Helper de path traversal guard**: `src/tools/_path_helpers.py`

### Corregido
- Manejo de errores unificado en API (formato JSON consistente)
- Limpieza de widgets al eliminar sesión
- Edge cases en la reconstrucción de historial
- Documentación: ARCHITECTURE.md y MODULES.md actualizados

---

## [v0.0.4] — 2026-06-11

### Agregado
- **Seguridad**:
  - Content-Security-Policy headers en todas las respuestas HTTP
  - SSRF validation en redirect chain de `fetch_url` (todos los hops intermedios)
  - Path traversal guard con `os.path.realpath` + `commonpath`
  - XSS escaping en `stream-renderer.js` (tool name) y `chat-form.js` (error reason)
  - Rate limiter por sesión en tools (30 calls / 10s window con LRU eviction)
  - Rate limiter HTTP (60 requests/min por IP)
  - `_local_only` guard en debug router (respeta env `TESTING`)
- **Base de datos**:
  - Migración `_migration_010` con índices + FK constraints en todas las tablas
  - `PRAGMA foreign_keys = ON` en `init_db()`
  - `_transaction()` context manager con rollback automático en excepción
  - Eliminación en cascada real (session delete limpia 4 tablas)
- **API**:
  - Pydantic models: `WidgetStatePayload`, `SaveWidgetPayload`, `ChatPayload`
  - Error format unificado: `{"detail": "..."}` JSON (3 formatos inconsistentes → 1)
- **Arquitectura**:
  - `__init__.py` en `src/`, `web/`, `web/routers/` (paquetes explícitos)
  - Lazy provider en `models.py` (no más OpenAI client en tiempo de import)
  - Lazy import de `src.tools` en compressor y context
  - `ToolLoopContext` dataclass (11 parámetros → 1 grupo)
  - `_try_fetch` pipeline con 4 funciones SRP en `fetch_url.py`
- **Backend**:
  - Logging estructurado con namespace `kairos.*`
  - `BackendLogHandler` (ring buffer en `web/logging.py`)
  - Docstrings en `repositories.py` (todos los métodos públicos)
  - Logging en `fetch_url.py`, `repositories.py`, `cli.py`
- **Frontend**:
  - CSP headers inline
  - Cap de 50 eventos en `KairosWidgets._debug`
  - Reset de estados de formulario al cambiar de sesión
  - CSS: migración de colores hardcodeados a custom properties en `:root`
  - CSS: eliminación de `!important` en toda la base
- **Tests**:
  - 198 tests nuevos (total 431: 233 heredados + 198 nuevos)
  - Coverage: repositorios, API, routers, tools, core, LLM, web services

### Corregido
- **BUG (crítico)**:
  - `manager.py`: `verify_model()` siempre fallaba (`model_id` → `model`)
  - `tool_loop.py`: sync path etiquetaba `content` como `reasoning`
  - `tool_loop.py`: append SDK object crudo en history (debía ser `dict`)
  - `tool_loop.py`: sync path no guardaba respuesta final en DB
  - `chat_sync.py`: ignoraba tool calls (no pasaba `tools=` al LLM)
  - `tool_loop.py`: `_yield_stream_fallback` no llamaba `_process_llm_stream`
- **BUG (DB)**:
  - Repositories sin rollback en excepción → transacciones huérfanas
  - Session delete no limpiaba 4 tablas → orphan rows
  - TOCTOU race en `SavedWidgetRepository.save()`
  - `chat_sync.py`: mensajes sin `session_id` → violación FK
- **BUG (XSS/SSRF)**:
  - `stream-renderer.js`: tool name sin escapar
  - `chat-form.js`: error reason sin escapar
  - `fetch_url`: redirect chain no validaba hops intermedios
- **BUG (info leak)**:
  - `widgets.py`: `detail=str(e)` exponía internals del server
  - `chat_stream.py`: error msg crudo al cliente
- **BUG (memory leak)**:
  - `_session_rate` sin evicción → crecía sin límite
  - `KairosWidgets._debug` sin cap de eventos
  - Estado de formulario persistía entre sesiones
- **BUG (CSS)**:
  - Colores hardcodeados, `!important` generalizado, sin variables
- **BUG (API)**:
  - Error format inconsistente (3 formatos distintos → unificado a JSON)
  - Sin Pydantic models en routers
  - Tipos de retorno incorrectos en varios endpoints
- **Typing**: ~80 anotaciones faltantes (tipos de retorno, parámetros)
- **Legacy**: referencias a archivos eliminados en docs

### Limpieza
- Dead code removido: `log_tool_call()`, `get_state()`, `_format_infoboxes()`, 5 funciones helpers huérfanas
- Archivos huérfanos eliminados: 3 archivos de módulos eliminados (memory/message.py legacy, etc.)
- 30+ imports sin usar removidos de tests
- Logger global acotado a namespace `kairos.*` (reemplazo de root logger)
- 16 refactors de funciones largas a helpers nombrados
- README.md: estructura actualizada con badges de coverage y tests
- Comentario engañoso en `_deps.py` removido
- CSS: eliminación masiva de `!important`

### Arquitectura (refactor mayor)
- **API Facade**: `src/api.py` ahora es el único entry point para web routers
- **Tool Loop Context**: `ToolLoopContext` dataclass reemplaza 11 parámetros sueltos
- **Provider Pattern**: `LLMProvider` Protocol + `OpenAIProvider` implementation
- **Repository Pattern**: `_BaseRepository` abstracto con `_transaction()` CM
- **Migrations**: 9 migraciones secuenciales, todas idempotentes
- **Dependency Wiring**: `src/core/_deps.py` centraliza partials para evitar circular imports

---

## [v0.0.5] — 2026-06-11

### Agregado
- **Auditoría de salud completa**: 9 áreas auditadas, 43 hallazgos documentados
- **Extracción de repositorios**: `src/memory/repos/` con 8 archivos individuales (6 repos en 1 archivo → 8 archivos)
- **Shim de retrocompatibilidad**: `repositories.py` convertido a shim (`from .repos import *`)
- **Formato de tools unificado**: `[OK]`/`[ERROR]` en las 10 tools (23 cambios en 10 archivos)
- **Sanitización frontend**: `escHtml()` helper, innerHTML seguro en iframe.js, chat-form.js, toolbar.js
- **CI actualizada**: stress test incluido en `test:js` y workflow CI
- **TOOLS.md auto-generado**: `load_context()` lo regenera desde `TOOL_DEFINITIONS`

### Corregido
- Re-exports muertos eliminados de `src/core/__init__.py` y `src/llm/__init__.py`
- `_provider_registry`/`register_provider` eliminado de `src/llm/models.py` (dead code)
- Endpoint `GET /new-session` eliminado (sin consumidores frontend)
- `session_id` movido de `cli.py` a `orchestrator.generate_session_id()`
- `KairosUtils.esc()` renombrado a `scrollToBottom()` (nombre engañoso)
- `.msg-interim` CSS eliminado (clase no utilizada)
- 7 assertions `"Success"` → `"[OK]"` en tests (por cambio de formato tools)
- Patch paths actualizados en `test_repositories.py`
- Re-exports necesarios restaurados para `test_llm.py` y `test_core.py`
- `validate_findings.py` eliminado (falsos positivos)

### Arquitectura
- **Sub-agentes paralelos**: 5 agentes ejecutados sin conflicto de archivos
- **Shim pattern**: refactor gradual sin romper imports existentes
- **`__all__` explícito**: cada archivo de `repos/` define su API pública

---

## [v0.0.18] — 2026-06-11

### Agregado
- Documentación de arquitectura completa (8 archivos)
- CHANGELOG: v0.0.8-v0.0.17 documentadas
- ROADMAP: completado v0.0.1-v0.0.17

---

## [v0.0.19] — 2026-06-11

### Corregido
- ESLint: /* global */ en 10 módulos JS
- CHANGELOG: v0.0.16 y v0.0.17 agregadas
- fetch .catch() en chat-stream.js y stream-fetcher.js

---

## [v0.0.20] — 2026-06-11

### Corregido
- ESLint 0 errores (38 fixes)
- Circular import tool_loop→api eliminado (save_message en _deps.py)
- Flaky test_web_logging.py fix (fixture autouse)
- CHANGELOG v0.0.18-v0.0.20

---

## [v0.0.21] — 2026-06-11

### Corregido
- history.py: import logging eliminado (no usado)
- loader.py: filtro `_` corregido para excluir helpers
- CHANGELOG: v0.0.18-v0.0.21 documentadas
- README: versión actualizada a v0.0.21

---

## [v0.0.6] — 2026-06-11

### Agregado
- **Ruff 71→0**: linting totalmente limpio (16 auto-fix + 55 manuales)
- **Pyright 16→0**: type checking sin errores
- **Refactor `tool_loop.py`**: extraídas `_process_stream_event()`, `_execute_tools()`, `_handle_fallback()`
- **Refactor `api.py`**: imports agrupados por fuente, funciones por propósito
- **Refactor `chat-form.js`**: 4 helpers extraídos, duplicación de reintento eliminada (3→1)
- **Refactor `toolbar.js`**: `createToolbarButton()` factoriza ~80 líneas de estilo duplicado
- **45 tests JS nuevos**: session (17), debug (15), chat-stream (13)

### Corregido
- `sanitize_widget_id` re-export faltante en `src/api.py`
- Tests JS: mocks DOM corregidos (navigator.clipboard, window.* vs global.*)
- `test-frontend-integration.js`: `esc` → `scrollToBottom`

### Cobertura final
- Python: 431 tests, Ruff 0, Pyright 0
- JS: 110 tests (65 existentes + 45 nuevos), ESLint 0

---

## [v0.0.7] — 2026-06-11

### Agregado
- **Refactor mayor de arquitectura**: context.py → package, history.py → 3 módulos, runner.py → 4 módulos
- **DatabaseEngine Protocol** + SQLiteEngine (abstracción para futuro multi-DB)
- **Provider injection**: `_PROVIDER_REGISTRY` + `register_provider()` + config env `LLM_PROVIDER`
- **Ciclo tools↔api roto**: 4 tools importan directo de repos
- **Ciclo toolbar↔iframe roto**: via iframe-builder.js + ui-helpers.js
- **stream-renderer.js** dividido en 3 handlers independientes (reasoning, content, tool_call)
- **chat-form.js**: extraídos retry-handler.js + stream-error-handler.js, eliminado monkey-patching
- **session.js**: IIFE KairosSession con backwards-compat
- **api.py**: 6 singletons → 1 lazy registry (~40 líneas menos)
- **cli.py + handler_cli.py**: ahora usan api.py como fachada

### Corregido
- Mock paths actualizados en 4 archivos de tests
- test_stream_abort_persistence.py reescrito para nueva firma
- test-stream-renderer.js carga content-handler.js

### Archivos nuevos (17)
- src/context/ (4), src/core/history_*.py (3), src/tools/_*.py (3), src/memory/engine.py + sqlite_engine.py (2)
- web/static/modules/ (5: reasoning-handler, content-handler, tool-call-renderer, retry-handler, stream-error-handler)
- web/static/modules/widgets/ui-helpers.js

### Cobertura
- Python: 431 tests, Ruff 0, Pyright 0
- JS: 108 tests

---

## [v0.0.8] — 2026-06-11

### Agregado
- **Migración a Vitest**: test runner JS unificado, configuración `vitest.config.js`, cobertura integrada
- **Type hints completos**: anotaciones de tipo en todos los módulos Python (parámetros, retorno, generics)
- **Error boundaries**: `try/except` con clasificación de errores en todos los routers web
- **API contract tests**: tests de integración que validan schemas Pydantic contra respuestas HTTP reales
- **Documentación**: `docs/API_REFERENCE.md` auto-generada desde docstrings

### Corregido
- Imports circulares menores resueltos en `src/core/_deps.py`
- Mock paths desactualizados en 12 archivos de tests JS

### Limpieza
- 87 líneas de dead code eliminadas en `src/llm/manager.py`
- Comentarios obsoletos removidos de `src/tools/runner.py`

---

## [v0.0.9] — 2026-06-11

### Agregado
- **Playwright E2E setup**: configuración inicial con Chromium, fixtures de sesión, helpers de test

### Corregido
- Tests JS: 15 mocks de DOM actualizados para entorno Vitest

### Limpieza
- **-1420 líneas**: eliminación masiva de código muerto, imports sin usar, funciones legacy no llamadas
- `src/memory/repositories.py` shim reducido a 3 líneas
- `src/core/history.py` facade simplificado
- 4 archivos de tests obsoletos eliminados

---

## [v0.0.10] — 2026-06-11

### Agregado
- **chat-form split**: `chat-form.js` dividido en `chat-form.js` (submission) + `input-handler.js` (input/tokens/shortcuts)
- **toolbar split**: `toolbar.js` dividido en `toolbar.js` (UI buttons) + `session-actions.js` (rename/delete/navigate)
- **Session error handling**: clasificación de errores de sesión (not found, locked, corrupt) con mensajes user-friendly
- **Dead code**: 23 funciones sin consumidores eliminadas de routers y services

### Corregido
- `input-handler.js`: `Enter` sin Shift no enviaba mensaje en Firefox
- `session-actions.js`: rename de sesión con caracteres especiales truncaba a 50 chars

### Limpieza
- `src/tools/loader.py`: 4 imports reordenados por dependencia
- CSS: 12 selectores huérfanos eliminados

---

## [v0.0.11] — 2026-06-11

### Agregado
- **api.py split (226→10 módulos)**: `src/api/` package con `__init__.py` como fachada + módulos individuales:
  - `messages.py`, `sessions.py`, `widgets.py`, `debug.py`, `tools.py`, `rebuild.py`, `filter.py`, `stream.py`, `repos.py`
- **E2E expansion (+11 specs)**: Playwright tests para chat, sesiones, widgets, debug, streaming, error recovery

### Corregido
- `api/__init__.py`: imports re-exportados restaurados para backward compat con routers existentes
- `test_api_contract.py`: 4 tests corregidos para nuevo import path

### Limpieza
- `src/api.py` legacy eliminado (era un shim)
- 6 `# type: ignore` innecesarios removidos

---

## [v0.0.12] — 2026-06-11

### Agregado
- **Dependency injection para circular imports**: `_Container` dataclass centraliza dependencias
- `src/core/_deps.py` reescrito con `provide()` pattern

### Corregido
- `src/core/orchestrator.py` ↔ `src/api/` circular import roto vía DI container
- `src/memory/repos/` ↔ `src/tools/runner.py` circular import roto vía `provide()`
- 3 tests que fallaban por import order修复

### Limpieza
- `_PROVIDER_REGISTRY` global eliminado de `src/llm/models.py`
- 8 `TYPE_CHECKING` imports innecesarios removidos

---

## [v0.0.13] — 2026-06-11

### Agregado
- **ES modules migration**: 24 archivos JS migrados de `<script>` globals a `import`/`export`
- **Vite configurado**: `vite.config.js` con proxy a FastAPI, HMR habilitado, build para producción
- **Module map**: `web/static/modules/index.js` como barrel export para todos los módulos

### Corregido
- `stream-dispatcher.js`: exports nombrados restaurados para compat con tests Vitest
- `chat-form.js`: `import` de `input-handler.js` corrige referencia undefined

### Limpieza
- `<script>` tags de `<script type="module">` en `base.html`
- `window.Kairos*` globals eliminados de 14 archivos

---

## [v0.0.14] — 2026-06-11

### Agregado
- **Security fixes**:
  - XSS: sanitización de `innerHTML` en `chat-form.js`, `toolbar.js`, `content-handler.js` vía `escHtml()`
  - Debug access: endpoint `/debug` ahora requiere header `X-Debug-Token` o env `TESTING=1`
- **Docker**: `Dockerfile` multi-stage (build + runtime), `docker-compose.yml` con volumen para DB
- **CI pipeline**: `.github/workflows/ci.yml` con lint + test + typecheck + build
- **Health check**: `GET /health` endpoint con status de DB, LLM provider, uptime

### Corregido
- `fetch_url.py`: SSRF guard ahora valida redirects intermedios (no solo el primer hop)
- `_session_rate` dict: evicción LRU limitada a 1000 entradas máximo

### Limpieza
- 3 `print()` statements de debug removidos de `src/cli.py`
- `_debug` flag en `KairosWidgets` limitado a 50 eventos

---

## [v0.0.15] — 2026-06-11

### Agregado
- **30 tests nuevos**: cobertura de edge cases en repositorios (concurrent writes, empty sessions, unicode)
- **DRY refactor**: helpers compartidos extraídos en `src/tools/_shared.py` (sanitize, validate, format)
- **Lazy lxml**: `lxml` importado bajo demanda en `fetch_url.py` (reduce startup time ~200ms)

### Corregido
- `tool_loop.py`: `_process_tool_turn()` no actualizaba `turn` counter en streaming path
- `message_persister.py`: `save_assistant_message()` no guardaba `prompt_tokens` cuando era 0
- `test_e2e_chat.py`: 2 assertions actualizadas para nuevo formato NDJSON

### Limpieza
- `src/core/history.py`: facade reducido a 5 imports (era 12)
- `src/tools/__init__.py`: exports reordenados alfabéticamente
- 4 docstrings redundantes eliminados de `src/memory/repos/base.py`
- CSS: `.tc-item` selectores consolidados (era 3 reglas, ahora 1)

---

## [v0.0.16] — 2026-06-11

### Agregado
- CHANGELOG.md: v0.0.8-v0.0.15 documentadas
- README.md: actualizado a v0.0.15, src/api/ package, Docker
- docs/ARCHITECTURE.md: actualizado con estructura actual

### Corregido
- N+1 transaction fix en _tool_persister.py
- 8 dead code items eliminados
- 3 fetches con .catch() agregados
- clipboard pattern unificado en debug.js
- script tags con defer en chat.html

## [v0.0.17] — 2026-06-11

### Agregado
- src/llm/models.py split → providers.py + model_state.py
- client.py: dedup retry logic con _with_fallback()
- stream-orchestrator.js split → stream-fetcher.js + stream-retry-coordinator.js
- SessionRepository.delete() refactor con delete_by_session()
- resolve_and_validate_path() en _path_helpers.py
- ESLint: parserOptions.sourceType: "module"

### Corregido
- getStreamTimeout() bug: retorna 30000ms en vez de null
- 3 fetches con .catch() agregados
- clipboard pattern unificado en debug.js
