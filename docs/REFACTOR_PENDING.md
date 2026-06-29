# Refactor Pendiente — node.py God Router y TS Migration

> **Fecha:** 2026-06-29
> **Estado:** Investigación completa. Pendiente de ejecución.
> **Scope:** Documentar el estado actual de dos áreas técnicas para retomar en otra sesión.

---

## 1. `web/routers/node.py` — God Router → ✅ SPLIT COMPLETADO

### Split ejecutado (2026-06-29)

```
web/
├── routers/
│   ├── node.py              (202 líneas) — state, runtime, heartbeat, promote, demote, event, sessions
│   ├── node_memory.py       (184 líneas) — memory/request, memory/queue, memory/flush,
│   │                                       sync/status, memory/snapshot, diagnostics
│   ├── node_failover.py     (23 líneas)  — failover/status
│   ├── _node_helpers.py     (96 líneas)  — 9 _get_* providers + _peer_cluster_state + _request_repos wrapper
│   └── _node_models.py      (27 líneas)  — NodeHeartbeatPayload, NodeEventPayload, NodeMemoryWritePayload
└── services/
    └── node_observability.py (95 líneas) — _runtime_mode, _memory_write_mode, _age_seconds,
                                              _lease_observability, _memory_observability
```

### Decisiones tomadas

- **Observability → `web/services/node_observability.py`** (no a `node_helpers.py`): son lógica pura de dominio, sin imports de FastAPI. Cumple la regla "framework concerns belong in web/" en sentido inverso — domain logic 100% pura.
- **Providers → `_node_helpers.py`** con underscore (convención de módulo privado en `web/routers/`, ya usada por `_memory_snapshot.py` y `_request_repos.py`). Auto-discovery los saltea.
- **`NodeRolePayload` ELIMINADO**: dead code desde su creación (commit `feac04d`). Los endpoints `/promote` y `/demote` nunca aceptaron body payload.
- **Tests no tocados**: el patch `web.routers.node._request_repos` (línea 147) sigue funcionando porque `from _node_helpers import _request_repos` enlaza el nombre en el namespace de `node.py`, y `mock.patch` hace `setattr` sobre esa attribute.
- **14 endpoints, 0 cambios de URL** — verificado con `create_app()` + inspección de rutas.

### Verificación

- 27/27 tests en `tests/unit/test_node_coordination.py` pasan (5.41s).
- `create_app()` registra 14 rutas `/api/node/*` idénticas a las originales.
- Sintaxis OK en los 6 archivos nuevos/modificados.

### Deuda futura (fuera de scope de este PR)

Los `_get_*` providers y `_request_repos` wrapper también están duplicados en `memory.py`, `sessions.py`, `pages.py`, `health.py` y `_memory_snapshot.py`. Centralizar esos duplicados no se hizo acá para no mezclar scope. Se dejó registrado para una pasada futura de consolidación de providers cross-router.

---

## 2. TS Migration — Estado actual

### Lo que está migrado (82 archivos `.ts` en `web/src_ts/`)

El frontend TS es el frontend de producción real. No convive con un frontend JS vanilla — ese ya no existe como aplicación.

#### Estructura migrada (completa):

```
web/src_ts/
├── api/          → ApiClient.ts (1 archivo)
├── core/
│   ├── debug/    → DebugManager, DomTreeSerializer, SystemLogPanel (3)
│   ├── infra/    → EventBus, Logger, LoggerFactory, LogUI, CSSInjector, DomContracts (6)
│   ├── notification/ → AudioBus, NotificationBell, NotificationService, RateLimitCooldown, ToastUI (5)
│   ├── session/  → SessionList, SessionStore (2)
│   ├── ui/       → ChatForm, FileUploader, GridController, Icons, RetryHandler (5)
│   └── widget/   → WidgetDetector, WidgetRegistry, WidgetStateManager (3)
├── rendering/    → DomRenderer, IframeBuilder, MessageView, MessageWindowing, WidgetContainerRenderer (5)
├── streaming/    → ContentHandler, NDJSONStreamClient, SSEClient, StreamDispatcher, StreamErrorHandler,
│                   StreamOrchestrator, StreamSimulator, error-renderer, reasoning-handler,
│                   tool-call-renderer (10)
├── types/         → 14 archivos de definiciones de tipos
├── widgets/       → CanvasCardManager, CanvasLayoutStore, CanvasOverlay, CanvasWorkspace,
│                   HealthOverviewPanel, LanStatusPanel, MemoryStatusPanel, ModelSelector,
│                   ModelAvailabilityPoller, SkillsUI, templates (11)
├── __tests__/     → 16 test files (vitest, 352 tests pasando)
└── app.ts         → Entry point que wirea todo via DI
```

#### Cómo se sirve

- **Template:** `web/templates/chat_ts.html` — sirve el build de Vite.
- **Build:** `vite build` compila `app.ts` → `web/static/dist/assets/*.js` (4 chunks: streaming, rendering, widgets, debug + `app.js`).
- **Pages router:** `web/routers/pages.py` usa `resolve_frontend_entry("app.js")` para servir chat_ts.html en las rutas principales (`/`, `/session/{id}`, `/debug`).
- **Router redirect `chat_ts.py`** — eliminado (ya no se necesita redirigir a `/chat-ts`, las URLs `/`, `/session/{id}` sirven directamente el template).

### ✅ Cierre cosmético completado (2026-06-29)

1. **`app_mock.ts` → `app.ts`** — renombrado. `vite.config.js`, `pages.py`, `tests/unit/test_anti_regression.py`, `tests/unit/test_regression_pipeline.py` actualizados. Bundle regenerado: `dist/assets/app.js`. 0 refs a `app_mock` en source/tests/docs.

2. **`model-availability.js`** — migrado a TS como `web/src_ts/widgets/ModelAvailabilityPoller.ts`. Preservó el polling de `/models/availability` cada 60s, el badge `rl-badge` y el banner `go-quota-warning`. Se eliminó la lógica de manipular `<option>`s del `<select>` invisible (dead code ahora que `ModelSelector` usa divs). Wireado en `app.ts` como bloque DI. Archive `web/static/model-availability.js` y la referencia en `chat_ts.html` eliminados.

3. **`chat_ts.py`** — router de redirect eliminado. La URL `/chat-ts` ya no existe (las rutas principales `/`, `/session/{id}` ya sirven el template TS correctamente).

4. **`README.md`** — línea *"Frontend: No build step, no bundles. HTML + CSS + JS vanilla (~2,000 lines total)"* actualizada a *"TypeScript + Vite build. 80+ TS modules under `web/src_ts/`..."*. La mención de *"CLI + Web dashboard (FastAPI + vanilla JS + Jinja2)"* actualizada a *"+ TypeScript frontend + Jinja2"*.

5. **`docs/ARCHITECTURE.md`** — la frase *"No DI container"* corregida: ahora explica la DI lightweight tanto en el composition root de Python (`web/app_factory.py` con ~18 Lego blocks) como en el de TypeScript (`web/src_ts/app.ts`).

6. **`docs/ARCHITECTURE_FRONTEND_TS.md` y `docs/BACKEND_MIGRATION.md`** — todas las refs a `app_mock.ts`/`app_mock.js` (12 ocurrencias) actualizadas a `app.ts`/`app.js`.

### Resumen actualizado

| Aspecto | Estado |
|---------|--------|
| Source TS migrado | ✅ Completo (83 archivos — sumado `ModelAvailabilityPoller.ts`) |
| Build de Vite | ✅ Funcionando (4 chunks + entry `app.js`) |
| Tests TS | ✅ 16 test files / 352 tests pasando |
| Frontend JS vanilla source | ✅ Eliminado (solo queda vendored: marked, purify, htmx) |
| Nombre `app_mock.ts` | ✅ Renombrado a `app.ts` |
| `model-availability.js` | ✅ Migrado a TS (`ModelAvailabilityPoller.ts`) |
| README actualizado | ✅ Refleja Vite + TS + DI ligero |
| `chat_ts.py` (redirect) | ✅ Eliminado |
| Docs de arquitectura | ✅ Updated refs (app.ts/app.js) |

### Conclusión final

La migración TS está cerrada. El source TS es el frontend de producción, los archivos JS vanilla de aplicación ya no existen, el bundle se llama `app.js` (sin prefijo "mock"), y los docs reflejan la realidad (Vite + DI lightweight explícito). Lo único pendiente fuera de este alcance es el renombramiento de DBs (`kairos_memory.db` ↔ `kairos_curated_memory.db`), que es alto riesgo y requiere orchestración de sync LAN.

---

## Resumen para próxima sesión

| Tarea | Esfuerzo | Riesgo | Estado |
|-------|----------|--------|--------|
| Split `node.py` en 3 routers + 1 service + 2 helpers | 2-3h | Medio (14 endpoints, URLs no cambian) | ✅ COMPLETADO 2026-06-29 |
| Renombrar `app_mock.ts` → `app.ts` | 15 min | Bajo | ✅ COMPLETADO 2026-06-29 |
| Migrar `model-availability.js` a TS | 30 min | Bajo | ✅ COMPLETADO 2026-06-29 (ModelAvailabilityPoller.ts) |
| Actualizar README (frontend TS + DI) | 30 min | Bajo | ✅ COMPLETADO 2026-06-29 |
| Eliminar `chat_ts.py` redirect | 10 min | Bajo | ✅ COMPLETADO 2026-06-29 |
| Renombrar DBs (`kairos_memory.db` ↔ `kairos_curated_memory.db`) | 1h | Alto (rompe sync LAN si se hace mal) | Pendiente |
