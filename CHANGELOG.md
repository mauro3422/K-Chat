# Changelog — K-Chat TypeScript Frontend

## [2026-06-16] — Refactor masivo: desacople total, lifecycle, SSE, tests

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

### Pendiente (no bloquea)

- ASR (voz) — 8 archivos JS, ~940 líneas
- Widget toolbar (editar/historial) — 4 archivos JS, ~290 líneas
- Conexión AI — solo reemplazar `StreamSimulator` por `NDJSONStreamClient.startStream()`
