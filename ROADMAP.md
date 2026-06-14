# Roadmap — K-Chat (Kairos)

> Current version: **v0.0.55** (2026-06-13)

## Philosophy

An agent that does just enough. No external plugins, no marketplaces, no complex gateways. Each piece is an independent file ("legos").

Kairos is not trying to be a copy of OpenClaw. It is born from the frustration of configuring a large platform, finding errors when trying to use it for real tasks, and wanting something more direct: a personal assistant that can chat, remember, use tools, show what it did, and iterate on its own project alongside the user.

The goal is to build a reliable core first: chat, memory, tools, streaming, debug, and the ability to evolve without fighting an opaque architecture. Future channels like Telegram, webhooks, or nightly tasks should be adapters around the same core, not a reason to turn the project into a bloated platform.

## Completado

### v0.0.1 — Core funcional
- [x] Chat funcional vía CLI y web
- [x] SQLite como motor de persistencia
- [x] Sistema de herramientas con auto-descubrimiento via `importlib`
- [x] Herramientas iniciales: `fetch_url`, `read_file`, `write_file`, `web_search`
- [x] Streaming básico de respuestas del LLM
- [x] Sistema de sesiones con UUID
- [x] Configuración vía `.env`

### v0.0.2 — Arquitectura Lego + Widgets
- [x] Arquitectura Lego: módulos independientes sin acoplamiento
- [x] Streaming real con NDJSON
- [x] Fallback resiliente para modelos caídos
- [x] Sistema de Widgets con DB versionada
- [x] UI Dashboard: sidebar, sesiones, fases colapsables
- [x] Tool `save_memory`, `read_skill`, ciclo de vida de widgets
- [x] Compresor de historial (>40 msgs / >6k tokens)
- [x] Auto-rename de sesiones vía LLM

### v0.0.3 — API Facade + Repository Pattern
- [x] API Facade: single entry point con 15+ funciones públicas
- [x] Repository Pattern: `_BaseRepository` + 6 repositorios tipados
- [x] Thread safety con `threading.Lock`
- [x] 9 migraciones idempotentes de esquema
- [x] 233 tests, linting ruff + pyright

### v0.0.4 — Seguridad completa
- [x] Content-Security-Policy headers
- [x] SSRF validation en redirect chain de `fetch_url`
- [x] Path traversal guard
- [x] XSS escaping en frontend
- [x] Rate limiter por sesión y HTTP
- [x] Migración 010: índices + FK constraints + cascada real
- [x] Pydantic models, error format unificado
- [x] Provider Pattern, ToolLoopContext, DI container
- [x] 431 tests, logging estructurado, dead code eliminado

### v0.0.5 — Auditoría de salud + refactor repos
- [x] Auditoría de salud: 9 áreas, 43 hallazgos
- [x] Extracción de repositorios a `src/memory/repos/` (8 archivos)
- [x] Shim de retrocompatibilidad
- [x] Formato de tools unificado `[OK]`/`[ERROR]`
- [x] TOOLS.md auto-generado desde `TOOL_DEFINITIONS`

### v0.0.6 — Linting limpio
- [x] Ruff 71→0, Pyright 16→0
- [x] Refactors: `tool_loop.py`, `api.py`, `chat-form.js`, `toolbar.js`
- [x] 45 tests JS nuevos (session, debug, chat-stream)
- [x] Cobertura: 431 Python + 110 JS tests

### v0.0.7 — Refactor mayor de arquitectura
- [x] `context.py` → package, `history.py` → 3 módulos, `runner.py` → 4 módulos
- [x] DatabaseEngine Protocol + SQLiteEngine
- [x] Provider injection con `LLM_PROVIDER` env
- [x] Ciclos tools↔api y toolbar↔iframe rotos
- [x] Frontend: stream-renderer dividido en 3 handlers independientes

### v0.0.8 — Vitest + Type hints
- [x] Migración a Vitest como test runner JS
- [x] Type hints completos en todos los módulos Python
- [x] Error boundaries en routers web
- [x] API contract tests
- [x] `docs/API_REFERENCE.md` auto-generada

### v0.0.9 — Playwright E2E + limpieza
- [x] Playwright E2E setup con Chromium
- [x] -1420 líneas de dead code eliminadas
- [x] Repositorios migrados a `src/memory/repos/` y shim eliminado

### v0.0.10 — Frontend split
- [x] `chat-form.js` dividido en submission + input-handler
- [x] `toolbar.js` dividido en UI + session-actions
- [x] Session error handling con mensajes user-friendly

### v0.0.11 — API split
- [x] `api.py` split en 10 módulos (`src/api/` package)
- [x] E2E expansion: +11 specs Playwright

### v0.0.12 — Dependency Injection
- [x] `_Container` dataclass centraliza dependencias
- [x] Circular imports resueltos vía DI container

### v0.0.13 — ES Modules + Vite
- [x] 24 archivos JS migrados a ES modules
- [x] Vite configurado con proxy a FastAPI y HMR
- [x] Module map barrel exports

### v0.0.14 — Seguridad + Docker
- [x] XSS sanitización en innerHTML
- [x] Debug endpoint con token/header
- [x] Dockerfile multi-stage + docker-compose.yml
- [x] CI pipeline: lint + test + typecheck + build
- [x] Health check endpoint `GET /health`

### v0.0.15 — Tests + DRY
- [x] 30 tests nuevos (edge cases repositorios)
- [x] DRY refactor: `_shared.py` con helpers compartidos
- [x] Lazy lxml en `fetch_url.py`

### v0.0.16-0.0.17 — Refactors + infraestructura
- [x] LLM Layer refactor: `providers.py`, `model_state.py`, shim backwards-compat
- [x] Frontend refactor: `stream-fetcher.js`, `stream-retry-coordinator.js`
- [x] Memory refactor: `delete_by_session()`, atomicidad con cursor
- [x] Tools DRY: `resolve_and_validate_path()` unificado
- [x] Dockerfile multi-stage con healthcheck
- [x] `.pre-commit-config.yaml` (ruff, eslint, hooks)
- [x] CI: Ruff + Pyright en workflow
- [x] requirements.txt con versiones pinneadas
- [x] 30 tests nuevos: tool_parser, rate_limiter, history_parser, etc.

### v0.0.18-0.0.21 — Documentation + cleanup
- [x] Architecture docs: 8 archivos de documentación técnica
- [x] CHANGELOG reestructurado (índice + archivos individuales)
- [x] ESLint 0 errores, circular import fix, flaky test fix
- [x] Widget code cache en DB: `widget_states` table con `_code_` entries
- [x] LLM models split, client dedup, SessionRepository

### v0.0.22 — Widget rendering fixes
- [x] `message_renderer.py`: inyecta `_code_` entries en `data-widget-states` para widgets inline
- [x] `content-handler.js`: deduplica widgets por key (evita duplicados html-widget + tag)
- [x] `content-handler.js`: skip `[Widget: key]` literals en texto (placeholders del AI)
- [x] `toolbar-core.js`: maneja 404 de version label graceful (verifica `r.ok`)
- [x] `iframe-builder.js`: envuelve código del widget en try-catch para SyntaxError
- [x] 470 tests Python pasan

### v0.0.23–0.0.28 — Widget stability, loop detector v2, facade cleanup
- [x] Widget rendering fixes, DOM ordering, loop detector v2
- [x] Contract hardening, bootstrap split, facade cleanup
- [x] Repository registry removed, DB lifecycle guard, sidebar decoupling

### v0.0.29–0.0.39 — Infrastructure hardening
- [x] Minor releases: logging, error handling, edge cases, frontend polish

### v0.0.40–0.0.44 — Decoupling phase
- [x] `chat_sync.py` delegates to `orchestrator.chat_stream()` (no more duplication)
- [x] Lazy imports removed from `tool_loop.py` → direct `MessageRepository`
- [x] Rate-limit retry decoupled to `src/llm/retry.py` + `src/constants.py`
- [x] Runtime de-compatibilized: shims removed from core, llm, api, memory
- [x] Docs aligned with actual runtime modules

### v0.0.45–0.0.46 — New tools
- [x] `execute_command`, `list_files`, `search_files`, `edit_file` as first-class tools
- [x] All aligned with safe path policy, documented and tested

### v0.0.47–0.0.49 — Repository injection chain
- [x] `orchestrator.py`, `tool_loop.py` accept `Repositories` dataclass (no direct instantiation)
- [x] `chat_stream_fn` inyectable en `web/services/chat_stream.py`
- [x] `src/api/messages.py`, `src/api/session.py` sin singleton de repos
- [x] `src/background_tasks.py` acepta `SessionRepository` inyectable

### v0.0.50–0.0.51 — Tool expansion
- [x] JS validation restored (`node --check`), brace globs `*.{py,js}`, mixed-language listings
- [x] `analyze_code` tool: deep Python AST inspection, call flow, per-file metrics

### v0.0.52 — Mega-refactor: Lego Architecture Consolidation
- [x] **ModelState class**: Thread-safe state encapsulation (failed/verified/cached models)
- [x] **Policy split**: `policy.py` → 4 sub-modules (discovery, verifier, selector, failover)
- [x] **Repos injection chain**: `chat.py` → `orchestrator.py` → `tool_loop.py` → `runner.py`
- [x] **`sqlite3.Row` row_factory**: Named column access + 38 migrations from positional
- [x] **Frontend cleanup**: CSS extraction, global removal, `log-ui.js` module, `shared-state.js`
- [x] **`git_operation` tool**: Safe Git ops (blocks `--force`/`--hard`), 16 tools total
- [x] **`MemoryIndexRepository`**: New repo for `memory_index` table
- [x] **Stream resilience**: Save retry (3 attempts, backoff), mid-stream recovery
- [x] **24 audit issues fixed**: 3 critical, 6 high, 9 medium, 6 low
- [x] **Tests**: 523 Python + 176 Vitest (0 failures), 0 ESLint errors

### v0.0.53 — Cache invalidation (2026-06-13)
- [x] **Context cache invalidation**: `save_memory` now invalidates `_CONTEXT_CACHE` and `_TOOLS_MD_CACHE`
- [x] System prompt refreshes with current MEMORY.md on each user message
- [x] SOUL.md, MEMORY.md, AGENTS.md, TOOLS.md all fresh in-session

### v0.0.54 — Lego hardening de backend y transición frontend (2026-06-13)
- [x] **Runtime sin wrappers viejos**: eliminados `src/api/{llm,models,history,health}.py` y `save_message()` legacy; los callers ya van a los módulos reales
- [x] **Historial tipado**: `HistoryMessage` como contrato estable; `rebuild_history()` exige `messages_repo` explícito
- [x] **Sesión y memoria**: cascade delete movido al repositorio; `conn_fn` salió del contrato de sesión
- [x] **Session delete explícito**: `delete_session()` y `SessionRepository.delete_cascade()` ya exigen `repos` explícito, sin fallback de resolución
- [x] **Memory lifecycle split**: el loop de migraciones salió de `schema.py` y quedó en `migration_runner.py`
- [x] **Contexto puro**: `load_context()` ya no escribe archivos; la generación de `TOOLS.md` quedó como paso explícito
- [x] **Tools y web**: el loader ya no dispara build al importar; routers y servicios web usan imports directos
- [x] **Session page hardening**: acciones de sesión renderizadas por DOM API y navegación encapsulada tras dependencia explícita
- [x] **Session page HTML parsing**: el render principal ya arma fragmentos DOM sin asignar `innerHTML` directo
- [x] **Session page snapshot DOM**: el cancel de borrado ya restaura un clon del nodo, no `outerHTML`
- [x] **Bootstrap nav injection**: `app.js` inyecta navegación explícita en `session-page.js` y `chat-form.js`
- [x] **Bootstrap session id**: `app.js` toma la sesión desde `#app[data-session-id]` en vez de `window.__SESSION_ID`
- [x] **Bootstrap ASR config**: la config inicial de ASR se setea por código en `app.js`, no desde el template
- [x] **Widgets messaging bootstrap**: `startMessageHandler()` quedó explícito y `app.js` le pasa `eventTarget` y `locationOrigin`
- [x] **Shared render helpers**: `markdown-renderer.js`, `sidebar-refresh.js` y `content-handler.js` ya pintan con fragmentos DOM en vez de asignar `innerHTML`
- [x] **Widget iframe builder**: `iframe-builder.js` ya monta loading/error con nodos DOM
- [x] **Debug panel hardening**: logs UI/stream/widgets/backend renderizados por DOM API, sin `innerHTML` en los listados principales
- [x] **Debug panel core render**: `refreshDebug()` armado con DOM explícito en lugar de concatenación HTML
- [x] **Sidebar refresh shared**: `refreshSidebar()` unificado en `sidebar-refresh.js` para session, stream y lifecycle
- [x] **Debug listeners injectable**: `bindDebugControls()` usa `eventTarget` inyectable en vez de depender de `window` directo
- [x] **Stream completion helper**: el post-success del stream salió de `stream-orchestrator.js` a `stream-completion.js`
- [x] **Retry message DOM**: `showRetryMessage()` y pill errors dejaron de usar `innerHTML` para la UI de error
- [x] **Tool call pills DOM**: `tool-call-renderer.js` dejó de pintar pills con `innerHTML`
- [x] **Reasoning DOM**: `reasoning-handler.js` dejó de crear el bloque inicial con `innerHTML`
- [x] **Content render seam**: `content-handler.js` delega el render principal en `replaceChildren`
- [x] **Markdown render seam**: `markdown-renderer.js` ya no usa `innerHTML` directo en `renderAll()`
- [x] **Markdown fallback cleanup**: `markdown-renderer.js` centralizó el fallback HTML en una sola función
- [x] **Sidebar render seam**: `sidebar-refresh.js` usa `replaceChildren` para pintar el sidebar
- [x] **Tool persister explícito**: `_persist_tool_results()` dejó de resolver repositorios por su cuenta y ahora recibe `repos` obligatorio
- [x] **Tool history explícito**: `get_tool_history` dejó de resolver `get_repos()` internamente y recibe `_repos` explícito
- [x] **Message render explícito**: `render_session_messages()` y `/sessions/{session_id}/messages` reciben `repos` explícito; el home/session page ya no hace discovery de modelos
- [x] **Frontend de transición final**: `session-page.js`, `chat-form.js`, `retry-handler.js` y `widgets/toolbar-editor.js` dejaron de depender de `innerHTML` directo en sus rutas críticas
- [x] **LLM docs sync**: mapas y arquitectura de `llm/` alineados con `adapters/openai_adapter.py`
- [x] **Health doc sync**: `docs/HEALTH.md` ya nombra `OpenAIAdapter` en vez de `OpenAIProvider`
- [x] **Frontend de transición acotado**: compatibilidad legacy aislada en `session-page.js`, `debug-panel.js` y `stream-orchestrator.js`
- [x] **Docs alineadas**: roadmap, audit lego y changelog actualizados con el estado real del refactor

### v0.0.55 — Lego UI & Layout Resizable (2026-06-13)
- [x] **Premium UI y Layout Resizable**: Estética Glassmorphism ligera, tema claro/oscuro (🌓) y gutter interactivo resizable con persistencia en `localStorage`.
- [x] **Lego Frontend**: Desacoplamiento total del renderizado de mensajes a JSON, inyectados dinámicamente desde el cliente (`message-renderer.js`).
- [x] **Performance Fix**: Throttling del debug panel en eventos de telemetría de voz ASR.
- [x] **Bug Fix**: Solucionado el fallo de scope de `os` en `db_query.py`.

### v0.0.56 — Telegram Bot + Watchdog (2026-06-13)
- [x] **Channel system**: `channels/` package con auto-descubrimiento, siguiendo el patrón Lego de `src/tools/`.
- [x] **Telegram adapter**: `channels/telegram/` — bot polling, handlers, adapter a `core.chat_stream()`.
- [x] **Watchdog daemon**: `.kairos/watchdog.py` — health check cada 5s, captura `git diff` + commits en crash, reinicia el servicio.
- [x] **Self-healing**: `error_context.md` escrito en crash → leído por `builder.py` en reinicio → inyectado en system prompt.
- [x] **Systemd services**: `k-chat.service`, `k-chat-watchdog.service`, `k-chat-telegram.service`.
- [x] **Config extendida**: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS`, `WATCHDOG_INTERVAL` en `.env`.

## Próximas features

| Priority | Area | What | Status |
|----------|------|------|--------|
| 1 | **UI modular + layout movible** | CSS partido en temas, gutter redimensionable, sidebar colapsable, layout responsive guardado en memoria | ✅ |
| 2 | **memory_search + list_memories** | Tools para consultar `MEMORY.md` de forma semántica (ahora con cache fresco) | 🔥 |
| 3 | **Auto-exploration + Docs sync** | Kairos analiza la arquitectura actual y sincroniza docs/ con el código real | 🔥 |
| 4 | **Inyección inteligente de memoria** | Sistema que inyecta recuerdos relevantes contextualmente antes de cada respuesta, basado en el tópico de la conversación | 📋 |
| 5 | **Telegram voice → ASR** | Conectar mensajes de voz de Telegram con el bridge ASR de DuckSugar | 📋 |
| 6 | **Widget Events → AI** | Widgets enviando acciones del usuario de vuelta al AI como contexto inyectado | 📋 |
| 7 | **Cross-Session Topic Tracer** | Rastreo de temas a través de múltiples sesiones (ahora con MEMORY.md confiable) | 📋 |
| 8 | **Temas visuales** | Matrix rain sidebar, fondos anime, burbujas custom, iconos temáticos, switcher de temas en UI | 📋 |
| 9 | **Session Export** | Exportar sesiones a Markdown o JSON | 📋 |
| 10 | **Scheduled Tasks** | Tareas programadas (cron-like) para automatizaciones | 📋 |
| 11 | **Nocturnal Agent** | Síntesis diaria de sesiones en `MEMORY.md` con contexto fresco | 📋 |
| 12 | **Proactive Insights** | Insights proactivos basados en patrones de uso | 📋 |
| 13 | **Discord Bot** | Segundo channel adapter siguiendo el patrón `channels/` | 📋 |
| 14 | **Widget versioning UI** | Mostrar versión actual del widget en toolbar sin fetch separado | 📋 |

> **Hecho**: Stream heartbeat (20s backend + 10s tools), cache de contexto invalidado (v0.0.53), watchdog auto-recuperación (v0.0.56), Telegram channel (v0.0.56)

## Architecture Decisions

| Decision | Chosen | Alternative |
|----------|--------|-------------|
| Runtime | Pure Python | TypeScript |
| LLM client | OpenAI SDK | httpx direct |
| Memory | Native SQLite + Markdown | sqlite-vec / external base |
| Stream | Sync generator | Async complex |
| Config | `.env` + Markdown | Large YAML |
| Tools | `importlib` auto-registry | Manual registration |
| Channels | `channels/` auto-discovery | Hardcoded adapters |
| Frontend | Vanilla JS + Vite | React / Vue / Svelte |
| Serialization | NDJSON | SSE |
| Growth | Channels as adapters | Heavy gateway from day one |
| DI | `_Container` dataclass | Framework injection |
| Crash recovery | Watchdog + error_context.md | Manual debugging |

## Guiding Principle

Kairos must grow from real utility, not from imitation. First it has to be a reliable helper for the user and for its own code; then it can add channels, automations, and external capabilities without losing readability.
