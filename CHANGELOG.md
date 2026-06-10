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
