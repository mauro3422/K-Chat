# Roadmap — K-Chat (Kairos)

> Current version: **v0.2.0** (2026-06-26)

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
- [x] **`git_operation` tool**: Safe Git ops (blocks `--force`/`--hard`), 33 tools total
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

### v0.0.57 — Lego Architecture: Deep Decoupling (2026-06-14)
- [x] **Tools↔context cycle broken**: `tools/` y `context/` ya no se importan mutuamente
- [x] **Arch analysis tools**: `analyze_code` con cyclomatic complexity, AST graph, cross-references
- [x] **Post-hooks**: validación arquitectónica post-commit via `_arch_checker.py`
- [x] **Skills modularizados**: `skills/` directory con SkillRegistry, auto-descubrimiento desacoplado
- [x] **pytest-testmon integrado**: tests incrementales, `gitignore` para testmondata

### v0.0.58 — File Attachments + Go Mode Models (2026-06-14)
- [x] **File Attachments UI**: subida de archivos en frontend con previsualización
- [x] **Go Mode Models**: selector de modelos con tiers Go/Free/Zen
- [x] **Rate limit tracker**: límites visibles en UI + anti-regression tests

### v0.0.59 — AGENTS.md cleanup + Architecture Constraints (2026-06-14)
- [x] **AGENTS.md reescrito**: reglas claras de arquitectura, constraints no-negociables
- [x] **Lego constraints documentadas**: sin singletons globales, sin acoplamiento ascendente
- [x] **Tool docs actualizadas**: alineadas con el registry real

### v0.0.60 — Memory System Overhaul (2026-06-16)
- [x] **RRF retrieval fix**: fusión rank-recíproca corregida para resultados híbridos
- [x] **Entity graph**: extracción y linking de entidades en memoria
- [x] **Batch embeddings**: procesamiento por lotes con fastembed
- [x] **Curator/Gardener/Tracer**: sistema de curación nocturna, poda de DBs
- [x] **Sesiones favoritas**: sistema de favoritos + síntesis nocturna
- [x] **Sistema de auto-inyección de memorias**: retrieval contextual antes de cada respuesta

### v0.0.61 — TS Frontend Migration + Model Selector (2026-06-17)
- [x] **Model Selector UI**: dropdown con SVGs de capacidades (razonamiento, tools, imagen, video, audio)
- [x] **Tier system**: Go Premium/Standard/Económico, Free — indicadores por color
- [x] **Dynamic ModelRegistry**: sin modelos hardcodeados, descubrimiento en runtime
- [x] **Real-time availability**: status dots con ping por modelo
- [x] **Desacople arquitectónico**: 4 Lego blocks backend, composition root, DI Fase 1-2
- [x] **TS frontend base**: migración de módulos JS → TS con bridge shims

### v0.0.62 — Stream + Debug migrados a TS (2026-06-17)
- [x] **Stream migration**: 7 bridge shims (stream-dispatcher, stream-fetcher, content-handler, tool-call-renderer, retry-handler, stream-orchestrator, log-ui)
- [x] **Debug unificado**: DebugManager.ts con logs backend/UI/stream/widgets, copy buttons, stream duration
- [x] **Vite config**: 7 nuevas TS entries, build 22 assets en 108ms
- [x] **96/96 TS tests pasando**

### v0.0.63 — Reranker ONNX + Notificaciones (2026-06-17)
- [x] **Reranker ONNX**: fastembed reemplaza PyTorch (~700MB → ~10MB, 4-5ms por inferencia)
- [x] **Sistema de notificaciones**: evento `"notification"` en NDJSON/SSE
- [x] **Retrieval sin auto-referencia**: filtro `exclude_source_key` para evitar duplicar MEMORY.md
- [x] **Contador de exchanges**: solo cuenta mensajes `role='user'`
- [x] **Recencia de memorias**: `last_accessed` y `query_count` actualizados en cada búsqueda

### v0.0.64 — Lifecycle Reset + Singleton Elimination (2026-06-18)
- [x] **18 módulos con configure_*/reset_***: LLM, Memory, Infra, Web — singleton elimination completa
- [x] **Bugs críticos corregidos**: corrutinas sin consumir, failover loop infinito, rate limiter global
- [x] **DI Composition Root**: SkillRegistry, RateLimiter, ToolRegistry a `app.state`
- [x] **Crash recovery extraído**: `context/crash_recovery.py` con detección de crash loop
- [x] **Memory upward coupling eliminado**: curator y archive sin imports de capas superiores

### v0.1.0 — Custom Model Selector + LAN Sync (2026-06-20)
- [x] **Model selector custom**: SVGs de capacidades, gutter drag (160-500px), dropdown inteligente
- [x] **LAN Sync / Federación**: coordinación de nodos, failover, health panels, peer memory
- [x] **Diagnóstico interactivo**: páginas de diagnóstico con memoria de pares, health overview
- [x] **DI Composition Root (Fase 3)**: singletons a `app.state`, LLM container, connection pool
- [x] **Multi-device SSE**: `KAIROS_WEB_URL` multi-URL, notificaciones a todos los dispositivos
- [x] **Telegram channel**: refactor completo con arquitectura Lego, reflexión entre UIs

### v0.1.1 — Test Stabilization (2026-06-20)
- [x] **74 backend failures fixed**: CanvasOverlay listener leak, import fixes, mock corrections
- [x] **fastembed instalado**: desbloquea 12 tests de embedding_service + reranker
- [x] **TestClient en context manager**: lifespan y mocks DI funcionando correctamente
- [x] **319 tests totales**: 16 suites, todos pasando

### v0.2.0 — Codex Task Bridge + LAN Remote Control (2026-06-26)
- [x] **Codex Task Bridge**: delegación de tareas entre agentes en LAN (`codex_task_bridge.py`, `delegate_to_codex.py`)
- [x] **LAN Remote Control**: sistema completo con smoke tests, nodos configurables, failover de modelos
- [x] **Descubrimiento LAN dinámico**: nodos se descubren sin IPs fijas, bind a interfaz activa
- [x] **Windows/Linux service hardening**: sin ventana de consola, restartable, lockfile atómico
- [x] **Idempotent memory migrations**: migraciones de esquema sin efectos secundarios

## Próximas features

| Priority | Area | What | Status |
|----------|------|------|--------|
| 1 | **Auto-exploration + Docs sync** | Kairos analiza la arquitectura actual y sincroniza docs/ con el código real | 🔥 |
| 2 | **Syncthing para sync multi-dispositivo** | MEMORY.md + memory.db sincronizados entre PC y laptop. Sessions.db local a cada máquina | ✅ |
| 3 | **Telegram voice → ASR** | Conectar mensajes de voz de Telegram con el bridge ASR de DuckSugar | 📋 |
| 4 | **Widget Events → AI** | Widgets enviando acciones del usuario de vuelta al AI como contexto inyectado | 📋 |
| 5 | **Cross-Session Topic Tracer** | Rastreo de temas a través de múltiples sesiones (ahora con MEMORY.md confiable) | 📋 |
| 6 | **Temas visuales** | Matrix rain sidebar, fondos anime, burbujas custom, iconos temáticos, switcher de temas en UI | 📋 |
| 7 | **Session Export** | Exportar sesiones a Markdown o JSON | 📋 |
| 8 | **Scheduled Tasks** | Tareas programadas (cron-like) para automatizaciones | 📋 |
| 9 | **Notturnal Agent + Memory Cells** | Sistema de cells background: Entity Extractor, Embedding Generator, Session Miner, Cross-Session Tracer | 📋 |
| 10 | **Proactive Insights** | Insights proactivos basados en patrones de uso | 📋 |
| 11 | **Discord Bot** | Segundo channel adapter siguiendo el patrón `channels/` | 📋 |
| 12 | **Widget versioning UI** | Mostrar versión actual del widget en toolbar sin fetch separado | 📋 |
| 13 | **Registro de dispositivos del usuario** | Guardar specs y config de cada dispositivo donde corre K-Chat para contexto del agente | 📋 |
| 14 | **Delegación remota fuera de LAN** | Codex bridge con transporte SSH/TLS para delegación fuera de casa | 📋 |

## Architecture Decisions
| Memory | 3 capas: MEMORY.md + memory.db (SQLite+sqlite-vec) + sessions.db (SQLite local) | PostgreSQL / sqlite-vec solo / todo en una DB |
| Sync multi-dispositivo | Syncthing (MEMORY.md + memory.db). Sessions.db local. MEMORY.md como source of truth, memory.db reconstruible | Nube centralizada / PostgreSQL remoto / Litestream |
| Agent duplicación | Primario/lectura por broadcast LAN + prioridad configuraable | Lock externo / solo un server permitido |
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
