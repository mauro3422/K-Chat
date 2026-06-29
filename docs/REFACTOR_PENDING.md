# Refactor Pendiente — node.py God Router y TS Migration

> **Fecha:** 2026-06-29
> **Estado:** Investigación completa. Pendiente de ejecución.
> **Scope:** Documentar el estado actual de dos áreas técnicas para retomar en otra sesión.

---

## 1. `web/routers/node.py` — God Router (519 líneas, 14 endpoints)

### Problema

`node.py` es el router más grande del proyecto (519 líneas) con 14 endpoints y ~8 helpers privados que mezclan tres dominios de responsabilidad distintos:

### Responsabilidades mezcladas

| Dominio | Endpoints | Helpers |
|----------|-----------|---------|
| **Coordinación de nodo** (rol, heartbeat, promote/demote) | `GET /state`, `GET /runtime`, `POST /heartbeat`, `POST /promote`, `POST /demote`, `POST /event` | `_get_coordinator`, `_get_node_bridge`, `_get_failover_state`, `_request_base_url`, `_peer_cluster_state`, `_runtime_mode` |
| **Memoria distribuida** (write queue, lease, snapshots) | `POST /memory/request`, `GET /memory/queue`, `POST /memory/flush`, `GET /sync/status`, `GET /memory/snapshot`, `GET /diagnostics` | `_get_memory_queue`, `_get_leader_lease_manager`, `_get_save_memory_run`, `_memory_write_mode`, `_age_seconds`, `_lease_observability`, `_memory_observability` |
| **Failover** (estado de promoción automática) | `GET /failover/status` | `_get_failover_state` |
| **Sesiones** (proxy a repos) | `GET /sessions` | `_request_repos` |

### Plan de split propuesto

```
web/routers/
├── node.py              (~120 líneas) — state, runtime, heartbeat, promote, demote, event, sessions
├── node_memory.py       (~200 líneas) — memory/request, memory/queue, memory/flush,
│                                         sync/status, memory/snapshot, diagnostics
├── node_failover.py     (~30 líneas)  — failover/status
└── node_helpers.py      (~80 líneas)  — _peer_cluster_state, _runtime_mode,
                                          _memory_write_mode, _age_seconds,
                                          _lease_observability, _memory_observability
```

Los helpers de observabilidad (`_runtime_mode`, `_memory_write_mode`, `_age_seconds`, `_lease_observability`, `_memory_observability`) deberían ir a `web/services/node_observability.py` — son lógica de negocio, no routing.

### Pydantic models

Los 4 models (`NodeHeartbeatPayload`, `NodeRolePayload`, `NodeEventPayload`, `NodeMemoryWritePayload`) viven hoy en `node.py`. Moverlos a `web/routers/_node_models.py` o a `src/api/` si se quieren compartir.

### Notas

- El router usa auto-discovery (`app_factory.py` escanea `web/routers/*.py`), así que agregar `node_memory.py` y `node_failover.py` los registra automáticamente — **no requiere tocar `app_factory.py`**.
- El prefix es `/api/node` (o similar). Verificar cómo se monta hoy el router antes de splittear.
- Los endpoints no cambian de URL — solo se mueven a archivos distintos.

---

## 2. TS Migration — Estado actual

### Lo que está migrado (82 archivos `.ts` en `web/src_ts/`)

El frontend TS es un **prototipo funcional completo** que convive con el frontend JS vanilla. No es una migración parcial de archivos sueltos — es un **frontend paralelo**.

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
│                   SkillsUI, templates (10)
├── __tests__/     → 16 test files (vitest)
└── app_mock.ts   → Entry point que wirea todo via DI
```

#### Cómo se sirve

- **Template:** `web/templates/chat_ts.html` — sirve el build de Vite.
- **Build:** `vite build` compila `app_mock.ts` → `web/static/dist/assets/*.js` (4 chunks: streaming, rendering, widgets, debug + app_mock.js).
- **Router:** `web/routers/chat_ts.py` — redirect de `/chat-ts` a `/`.
- **Pages router:** `web/routers/pages.py` usa `resolve_frontend_entry("app_mock.js")` para servir el chat_ts.html en las rutas principales (`/`, `/session/{id}`, `/debug`).

### Lo que falta

1. **El nombre `app_mock.ts`** sugiere que es un prototipo/mock, pero ya es el frontend de producción. Renombrar a `app.ts` (y actualizar `vite.config.js`, `pages.py`).

2. **`web/static/model-availability.js`** — único archivo JS vanilla que no se migró. Es chico pero queda fuera del build de Vite. Migrar a TS o dejarlo como vendor (decisión).

3. **El frontend JS vanilla (`web/static/`)** — no existe como source. Los únicos JS en `web/static/` son: vendored (`marked.min.js`, `purify.min.js`, `htmx.min.js`), el build output (`dist/`), y `model-availability.js`. **La migración TS está COMPLETA** en términos de source — no hay archivos `.js` de aplicación sin migrar.

4. **Decisión arquitectónica pendiente:** el TS frontend usa DI explícito (EventBus, LoggerFactory, etc.) mientras que el README dice "No DI container". Actualizar README para reflejar que el frontend TS sí usa DI ligero.

5. **`web/routers/chat_ts.py`** — un redirect de 8 líneas. Se podría eliminar si las rutas en `pages.py` sirven directamente el template correcto.

### Resumen

| Aspecto | Estado |
|---------|--------|
| Source TS migrado | ✅ Completo (82 archivos) |
| Build de Vite | ✅ Funcionando (4 chunks + entry) |
| Tests TS | ✅ 16 test files pasando |
| Frontend JS vanilla source | ✅ Eliminado (solo queda vendored) |
| Nombre `app_mock.ts` | ⚠️ Renombrar a `app.ts` |
| `model-availability.js` | ⚠️ Migrar o declarar vendor |
| README actualizado | ❌ Dice "no build step" pero hay Vite + TS |
| `chat_ts.py` (redirect) | ⚠️ Eliminable |

### Conclusión

La TS migration **está más completa de lo que parece**. No es "a medias" — el source TS es el frontend real y el JS vanilla ya no existe como aplicación. Lo que falta es **cierre cosmético**: renombrar `app_mock.ts`, migrar `model-availability.js`, alinear el README, y limpiar el redirect de `chat_ts.py`.

---

## Resumen para próxima sesión

| Tarea | Esfuerzo | Riesgo |
|-------|----------|--------|
| Split `node.py` en 3 routers + 1 service | 2-3h | Medio (14 endpoints, pero URLs no cambian) |
| Renombrar `app_mock.ts` → `app.ts` | 15 min | Bajo |
| Migrar `model-availability.js` a TS | 30 min | Bajo |
| Actualizar README (frontend TS + DI) | 30 min | Bajo |
| Eliminar `chat_ts.py` redirect | 10 min | Bajo |
| Renombrar DBs (`kairos_memory.db` ↔ `kairos_curated_memory.db`) | 1h | Alto (rompe sync LAN si se hace mal) |
