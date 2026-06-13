# Resumen Ejecutivo — Arquitectura K-Chat

**Versión:** 0.0.52 | **Fecha:** 2026-06-11 | **LOC total:** ~14.154 (src: 3.775 · web: 2.630 · tests: 7.749)

---

## 1. Visión General

K-Chat (nombre interno: Kairos) es un asistente conversacional con capacidades de herramientas, streaming en tiempo real y un sistema de widgets interactivos. Funciona como un chatbot autónomo que puede buscar web, leer/escribir archivos, gestionar memoria persistente y generar componentes HTML auto-contenidos.

**Stack:** Python (FastAPI) + SQLite + Vanilla JS (ES modules + Vite). Sin framework frontend. Sin DI container. Arquitectura "Lego": bloques independientes conectados por interfaces mínimas.

**Capacidades clave:**
- Chat con streaming NDJSON (razonamiento → herramientas → contenido)
- 16 herramientas auto-descubiertas (fetch_url, web_search, read_file, write_file, save_memory, read_skill, save_widget, update_widget, get_widget_code, get_tool_history, list_files, execute_command, search_files, edit_file, analyze_code, git_operation)
- Sistema de widgets versionados con persistencia de estado por sesión
- Auto-rename de sesiones vía LLM en background
- Compresión automática de historial (>40 msgs / >6k tokens)

---

## 2. Mapa de Módulos y Dependencias

```
ENTRY POINTS
├── src/cli.py                  (CLI REPL)
└── web/server.py               (FastAPI + middleware)

API FACADE
└── src/api/                    (módulos de dominio, sin agregador)
    ├── messages.py, session.py, widgets.py, debug.py
    ├── tools.py, history_parser.py, history_rebuilder.py, history_ui.py
    ├── session_contract.py     (dep bundle para CRUD/cascade de sesión)
    ├── widgets_contract.py     (dep bundle para state + widgets oficiales)
    ├── debug_contract.py       (dep bundle para debug + ASR telemetry)
    ├── history_contract.py     (dep bundle para rebuild_history)

CORE (cerebro)
├── src/core/orchestrator.py    (chat loop principal)
├── src/core/orchestrator_contract.py (dep bundle para el orquestador)
├── src/core/tool_loop.py       (ciclo razonamiento↔herramientas, max 25 turns)
├── src/core/history_parser.py   (parseo de rows)
├── src/core/history_rebuilder.py (reconstrucción LLM-ready)
├── src/core/history_ui.py       (filtrado UI + matching)

LLM (abstracción de modelo)
├── src/llm/protocol.py         (LLMProvider Protocol)
├── src/llm/openai_provider.py  (adapter OpenAI SDK)
├── src/llm/api_call.py         (_api_call retry wrapper)
├── src/llm/client.py           (chat + chat_stream)
├── src/llm/discovery.py        (model discovery/listing)
├── src/llm/verifier.py         (verify_model health checks)
├── src/llm/selector.py         (default model selection)
├── src/llm/failover.py         (model failover coordination)
├── src/llm/providers.py        (_PROVIDER_REGISTRY, register_provider)

TOOLS (sistema de herramientas)
├── src/tools/__init__.py       (auto-loader: TOOLS, TOOL_MAP)
├── src/tools/runner.py         (ThreadPoolExecutor, rate limiter)
├── src/tools/loader.py         (importlib filesystem scan)
├── src/tools/_path_helpers.py  (path traversal guard)
├── src/tools/_widget_helpers.py
└── src/tools/*.py              (16 herramientas individuales)

MEMORY (persistencia)
├── src/memory/lifecycle.py    (estado de inicialización por ruta)
├── src/memory/connection_pool.py (SQLite WAL, PooledConnection)
├── src/memory/schema.py        (init + migrations)
├── src/memory/repos/           (7 repositorios tipados)
│   ├── base.py                 (_BaseRepository + _transaction())
│   ├── message_repository.py
│   ├── session_repository.py
│   ├── tool_call_repository.py
│   ├── widget_state_repository.py
│   ├── debug_repository.py
│   └── saved_widget_repository.py
├── src/memory/migrations.py    (9 migraciones idempotentes)
└── src/memory/sqlite_engine.py (DatabaseEngine Protocol)

CONTEXT (ensamblaje de prompt)
├── src/context/builder.py      (build_system_prompt)
├── src/context/files.py        (load/read files)
├── src/context/templates.py    (SOUL/MEMORY/AGENTS defaults)
└── src/context/tools_docs.py   (TOOLS.md auto-generado)

CONFIG
├── src/config_loader.py        (Config dataclass, load_config, DEFAULT_CONFIG)
├── src/paths.py                (path constants: DATA_DIR, DB_PATH, STATIC_DIR)
├── src/constants.py            (MAX_TOOL_TURNS, LLM_MAX_RETRIES)
├── src/compressor.py           (compresión automática de historial)
├── src/background_tasks.py     (auto-rename vía LLM)
└── src/handler_cli.py          (comandos CLI: /model, /clear, /help)

WEB (dashboard)
├── web/routers/                (chat, pages, sessions, widgets, debug, health, asr, logs)
├── web/services/               (chat_stream, message_persister, error_classifier, renderer, loop_detector, file_logger, stream_retry_handler, asr_service)
├── web/static/modules/         (36 módulos ES: stream-dispatcher, handlers, forms, utils, widgets)
└── web/logging_handler.py      (BackendLogHandler ring buffer)
```

**Dirección de dependencias:** `entry → api → core → llm/tools/memory/context → config`. Sin dependencias circulares en runtime; cualquier compatibilidad vieja quedó confinada a facades o fue eliminada.

---

## 3. Flujo de Datos Principal (Mensaje → Respuesta)

```
[1] Usuario escribe → POST /chat/{session_id}
    │
[2] web/routers/chat.py → ChatPayload (Pydantic)
    │
[3] api.chat_stream() → orchestrator.chat_stream()
    │
[4] rebuild_history(session_id) → DB rows → history_parser → LLM messages
    │
[5] build_system_prompt(model) → SOUL.md + MEMORY.md + AGENTS.md + meta
    │
[6] src.llm.client.chat_stream() → LLM streaming chunks
    │
[7] _process_chunks() → si tool_call detectado:
    │   └→ runner.run_parallel_tools() → ThreadPoolExecutor
    │       ├→ _tool_parser.parse()
    │       ├→ _rate_limiter.check() (30/10s per session)
    │       └→ _tool_persister.save() → DB
    │   └→ append result → ¿más turns? (max 5)
    │
[8] yield ("content", token) → NDJSON stream
    │
[9] message_persister.save_assistant_message() → DB
    │
[10] auto_rename_session() → LLM background
     │
[11] Frontend: stream-dispatcher.js → reasoning-handler / content-handler / tool-call-renderer
     └→ DOM: <details> reasoning + .tc-item pills + .msg-body tokens
```

---

## 4. Patrones de Diseño

| Patrón | Aplicación |
|--------|-----------|
| **Facade** | `src/api/` — único entry point para web routers |
| **Protocol (duck typing)** | `LLMProvider`, `DatabaseEngine` — intercambiables |
| **Repository** | 7 repos en `src/memory/repos/`, base abstracta `_BaseRepository` |
| **Context Manager** | `_transaction()` con rollback automático |
| **Provider/Registry** | `_PROVIDER_REGISTRY` + `register_provider()` para LLMs dinámicos |
| **Lazy Singleton** | `_get_provider()`, `_get_conn()` |
| **Auto-discovery** | `importlib` scan en `tools/loader.py` |
| **Event Emitter** | `KairosStream` en frontend (on/emit) |
| **Dataclass** | `ToolLoopContext` (11 params → 1 objeto), `StreamGeneratorDeps`, `StreamState`, `MessageRecord` |
| **Shim** | Ninguno en runtime; lo que queda es documentación histórica |
| **Strategy** | `execute_action` meta-tool (una interfaz, N acciones) |
| **Rate Limiting** | Per-session (tools) + per-IP (HTTP) con LRU eviction |

---

## 5. Decisiones de Arquitectura Clave

| Decisión | Elección | Razón |
|----------|----------|-------|
| Runtime | Python puro | Simplicidad, ecosistema LLM |
| Frontend | Vanilla JS + ES modules | Sin build tools pesados, sin framework lock-in |
| Stream | NDJSON sync generator | Simpleza sobre async (FastAPI maneja el threading) |
| DB | SQLite + WAL | Embedded, zero-config, suficiente para single-user |
| Provider LLM | Protocol + registry | Extensible sin modificar core |
| Tools | importlib auto-discovery | Nuevo tool = nuevo archivo, zero config |
| Widgets | iframes sandboxed | Aislamiento de código arbitrario del LLM |
| Memory | Markdown files (SOUL/MEMORY/AGENTS) | Legible por humanos y LLMs |
| Compresión | Automática (>40 msgs / >6k tokens) | Control de costo sin intervención manual |
| Seguridad | CSP + SSRF guard + path traversal + rate limit | Defense in depth |
| Config | `.env` + Markdown | Mínimo overhead de configuración |
| Testing | 532 Python + 22 E2E (Playwright) | Cobertura amplia multi-capa |

---

## 6. Score de Salud por Área

| Área | Métrica | Score | Estado |
|------|---------|-------|--------|
| **Código Python** | Ruff 0 errores, Pyright 0 errores | 10/10 | Limpio |
| **Tests Python** | 532 tests, todos coleccionan | 9/10 | Sin E2E automatizado en CI completo |
| **Tests JS** | 22 E2E test suites (Playwright) | 8/10 | Playwright setup inicial |
| **Seguridad** | CSP, SSRF, XSS, rate limit, path guard | 9/10 | Audit v0.0.15 |
| **Documentación** | ARCHITECTURE.md, MODULES.md, API_REFERENCE.md | 8/10 | Auto-generada |
| **Arquitectura** | Sin circular deps en runtime, compatibilidad reducida | 9/10 | Refactor acumulado |
| **DB** | 7 repos, 9 migraciones, FK constraints | 9/10 | Transactions con rollback |
| **Frontend** | ES modules, event dispatcher, 36 módulos | 8/10 | Vanilla JS (sin type safety) |
| **Infra** | Docker, CI pipeline, health check | 7/10 | Básico pero funcional |
| **Deuda técnica** | v0.0.51 debt fixes, dead code cleanup | 8/10 | En mejora continua |
| **Overall** | | **8.5/10** | Sólido para v0.x |

---

## 7. Recomendaciones

### Corto plazo (v0.1.x)
- **Tests E2E completos:** Completar cobertura Playwright para flujos de widgets y error recovery
- **Tipado frontend:** Considerar JSDoc `@type` annotations en módulos JS (sin migrar a TypeScript)
- **Health check expansion:** Agregar métricas de latencia LLM y uso de herramientas al endpoint `/health`

### Mediano plazo (v0.2.x)
- **Multi-provider:** Implementar un segundo `LLMProvider` (Anthropic, local) para validar el patrón de registry
- **Background jobs:** Migrar auto-rename y compresión a un sistema de colas (Redis/RQ) si crece la carga
- **Rate limiting persistente:** Si hay múltiples instancias, migrar de dict en memoria a Redis

### Largo plazo
- **API versioning:** Preparar `/api/v1/` antes de romper contratos
- **WebSockets:** Considerar para bidireccional real-time (vs NDJSON unidireccional)
- **Plugin system:** Generalizar el patrón de tools para permitir plugins externos
- **Observabilidad:** OpenTelemetry tracing end-to-end (request → LLM → tool → response)

---

*Documento generado automáticamente desde ARCHITECTURE.md, MODULES.md, CHANGELOG.md y métricas del proyecto.*
