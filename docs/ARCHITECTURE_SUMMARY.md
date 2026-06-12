# Resumen Ejecutivo — Arquitectura K-Chat

**Versión:** 0.0.17 | **Fecha:** 2026-06-11 | **LOC total:** ~14.154 (src: 3.775 · web: 2.630 · tests: 7.749)

---

## 1. Visión General

K-Chat (nombre interno: Kairos) es un asistente conversacional con capacidades de herramientas, streaming en tiempo real y un sistema de widgets interactivos. Funciona como un chatbot autónomo que puede buscar web, leer/escribir archivos, gestionar memoria persistente y generar componentes HTML auto-contenidos.

**Stack:** Python (FastAPI) + SQLite + Vanilla JS (ES modules + Vite). Sin framework frontend. Sin DI container. Arquitectura "Lego": bloques independientes conectados por interfaces mínimas.

**Capacidades clave:**
- Chat con streaming NDJSON (razonamiento → herramientas → contenido)
- 10 herramientas auto-descubiertas (fetch_url, web_search, read_file, write_file, save_memory, read_skill, save_widget, update_widget, get_tool_code, get_tool_history)
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
    ├── tools.py, history.py, chat.py

CORE (cerebro)
├── src/core/orchestrator.py    (chat loop principal)
├── src/core/tool_loop.py       (ciclo razonamiento↔herramientas, max 5 turns)
├── src/core/history.py         (reconstrucción + filtrado UI)
├── src/core/chat_sync.py       (wrapper síncrono CLI)
└── src/core/_deps.py           (removed)

LLM (abstracción de modelo)
├── src/llm/protocol.py         (LLMProvider Protocol)
├── src/llm/openai_provider.py  (adapter OpenAI SDK)
├── src/llm/models.py           (registry, retry, fallback)
├── src/llm/client.py           (chat + chat_stream)
├── src/llm/policy.py           (descubrimiento, verificación)

TOOLS (sistema de herramientas)
├── src/tools/__init__.py       (auto-loader: TOOLS, TOOL_MAP)
├── src/tools/runner.py         (ThreadPoolExecutor, rate limiter)
├── src/tools/loader.py         (importlib filesystem scan)
├── src/tools/_path_helpers.py  (path traversal guard)
├── src/tools/_widget_helpers.py
└── src/tools/*.py              (10 herramientas individuales)

MEMORY (persistencia)
├── src/memory/connection.py    (SQLite WAL, PooledConnection)
├── src/memory/schema.py        (init + migrations)
├── src/memory/repos/           (6 repositorios tipados)
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

WEB (dashboard)
├── web/routers/                (chat, pages, sessions, widgets, debug, health)
├── web/services/               (chat_stream, message_persister, error_classifier, renderer)
├── web/static/modules/         (12 módulos ES: stream-dispatcher, handlers, forms, utils)
└── web/logging.py              (BackendLogHandler ring buffer)
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
| **Repository** | 6 repos en `src/memory/repos/`, base abstracta `_BaseRepository` |
| **Context Manager** | `_transaction()` con rollback automático |
| **Provider/Registry** | `_PROVIDER_REGISTRY` + `register_provider()` para LLMs dinámicos |
| **Lazy Singleton** | `_get_provider()`, `_get_conn()` |
| **Auto-discovery** | `importlib` scan en `tools/loader.py` |
| **Event Emitter** | `KairosStream` en frontend (on/emit) |
| **Dataclass** | `ToolLoopContext` (11 params → 1 objeto), `StreamState`, `MessageRecord` |
| **Legacy Compatibility** | `_deps.py` — eliminado; ya no forma parte del runtime |
| **Shim** | `history.py` — backward compat gradual |
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
| Testing | 470 tests (Python + JS) + Vitest + Playwright | Cobertura amplia multi-capa |

---

## 6. Score de Salud por Área

| Área | Métrica | Score | Estado |
|------|---------|-------|--------|
| **Código Python** | Ruff 0 errores, Pyright 0 errores | 10/10 | Limpio |
| **Tests Python** | 431 tests, todos coleccionan | 9/10 | Sin E2E automatizado en CI completo |
| **Tests JS** | ~110 tests (Vitest), ESLint 0 | 8/10 | Playwright setup inicial |
| **Seguridad** | CSP, SSRF, XSS, rate limit, path guard | 9/10 | Audit v0.0.15 |
| **Documentación** | ARCHITECTURE.md, MODULES.md, API_REFERENCE.md | 8/10 | Auto-generada |
| **Arquitectura** | Sin circular deps en runtime, compatibilidad reducida | 9/10 | Refactor acumulado |
| **DB** | 6 repos, 9 migraciones, FK constraints | 9/10 | Transactions con rollback |
| **Frontend** | ES modules, event dispatcher, 12 módulos | 8/10 | Vanilla JS (sin type safety) |
| **Infra** | Docker, CI pipeline, health check | 7/10 | Básico pero funcional |
| **Deuda técnica** | v0.0.17 debt fixes, dead code cleanup | 8/10 | En mejora continua |
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
