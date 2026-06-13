# Arquitectura Frontend — K-Chat

## 1. Qué hace cada módulo

| Módulo | Rol |
|--------|------|
| `app.js` | Entry point del bundle. Ensambla el runtime y delega globals de compatibilidad a los bootstraps. |
| `session-context.js` | CRUD de sesiones, sidebar refresh y binding del selector de modelo via HTMX + fetch. |
| `debug.js` | Panel de debug: log de eventos stream/UI, inspección de razonamiento/tools/system prompt, logs backend. |
| `chat-stream.js` | Bootstrap: inicializa `KairosWidgets`, `KairosForm`, provee `loadSession()` para SPA-like navigation. |
| `utils.js` | Utilidades globales: `escHtml`, `scrollToBottom`, `showToast`, handlers de error global. |
| `markdown-renderer.js` | Renderiza Markdown vía `marked` + `DOMPurify`, detecta/extrae widgets HTML inline, maneja footnotes. |
| **`stream-dispatcher.js`** | **Event bus central**: `on/emit/off` para eventos `content`, `reasoning`, `tool_call`, `error`, `heartbeat`. |
| `stream-orchestrator.js` | Orquesta un stream completo: crea `errorHandler`, timeout, llama `executeStreamFetch`, maneja retry final y limpieza. |
| `stream-fetcher.js` | Ejecuta `fetch` POST al backend, lee el stream SSE línea a línea, emite eventos al dispatcher. |
| `stream-lifecycle.js` | Maneja el ciclo de vida del stream: inicio, heartbeats, fin, limpieza. |
| `stream-retry-coordinator.js` | Intermediario entre orchestrator y retry-handler: decide si reintentar y delega a `scheduleRetry`. |
| `chat-form.js` | Captura submit del form, crea DOM del mensaje usuario/asistente, dispara `StreamOrchestrator.startStream`. |
| `chat-form-bootstrap.js` | Bootstrap de compatibilidad para `KairosForm`. |
| `retry-handler.js` | Estado de reintentos: count, max (3), delay backoff (2s * intento), `shouldRetry`, `scheduleRetry`. |
| `stream-error-handler.js` | Crea closures para capturar errores del stream, marca pills de tool como error, muestra card de reintento. |
| `content-handler.js` | Listener de `content`: acumula tokens, detecta widgets (`html-widget`/`[Widget:]`), re-renderiza markdown por fase. |
| `content-renderer.js` | Renderizado modular de contenido markdown con detección de widgets. |
| `reasoning-handler.js` | Listener de `reasoning`: crea `<details>` colapsable por fase de razonamiento, acumula tokens. |
| `reasoning-state.js` | Estado compartido de razonamiento entre fases. |
| `tool-call-renderer.js` | Listener de `tool_call`: renderiza pills de herramientas (calling → ok/error) agrupadas por fase. |
| `shared-state.js` | Estado compartido del stream (asstDiv, bodyDivs, phase state). |
| `dom-contracts.js` | Contratos DOM para elementos del chat. |
| `logger.js` | Logging de UI y stream para el panel de debug. |
| `asr-mic.js` | Integración de micrófono y ASR. |
| `widget-container-renderer.js` | Renderizado de contenedores de widgets. |
| `stream-bootstrap.js` | Bootstrap de compatibilidad para `window.StreamOrchestrator`. |
| `log-ui.js` | Logging de eventos UI para el panel de debug. |
| `stream-context.js` | Gestión del contexto del stream (sesión, modelo, estado). |
| `stream-contract.js` | Contratos de eventos y tipos del protocolo NDJSON/SSE. |

## 2. Sistema de streaming: Flujo token → DOM

```
[Backend SSE]
     │
     ▼
stream-fetcher.js          ← fetch() + ReadableStream, parsea JSON lines
     │ msg = {t: "content"|"reasoning"|"tool_call"|"heartbeat"|"error", d: "..."}
     ▼
stream-dispatcher.js       ← emit(msg.t, msg.d, shared-state.js)
     │
     ├─→ reasoning-handler  ← crea <details class="reasoning">, append token
     ├─→ content-handler    ← acumula token en shared-state.contentTexts[phase],
     │                       detecta widgets, parsea markdown, sanitiza con DOMPurify
     ├─→ tool-call-renderer ← renderiza pills calling/ok/error por tool
     ├─→ stream-error-handler ← captura errores type+message
     └─→ stream-lifecycle    ← maneja heartbeat/end/timeout
```

**State compartido** (en `shared-state.js`, creado en `stream-orchestrator.js`):
```js
{ asstDiv, bodyDivs[], reasoningEls[], contentTexts[], reasoningText, firstToken }
```

## 3. Sistema de retry

```
Error en stream o respuesta vacía
     │
     ▼
orchestrator.js → attemptRetry() → retry-coordinator
     │
     ▼
retry-handler.shouldRetry(hasContent, hasSuccessfulTools)
  │  count < 3 && !hasContent && !hasSuccessfulTools
  │
  ├─ SÍ → scheduleRetry(): delay 2s*count → dispatchEvent('submit') → re-envía
  │
  └─ NO → stream-error-handler.showRetryMessage() → card con botón "Reintentar"
```

**Tipos que NO reintentan**: `auth` (401), `rate_limit` (429) — se muestran directamente.

## 4. Event bus (`stream-dispatcher.js`)

```js
KairosStream.on('content', (token, state) => { ... });
KairosStream.emit('content', token, state);
KairosStream.off('content', callback);
```

- **Eventos**: `reasoning`, `content`, `tool_call`, `error`, `heartbeat`
- **Patrón**: Pub/sub síncrono, listeners en array, try/catch individual por listener
- **Registros default** en el dispatcher: `logStream()` y `logUI()` para debug

## 5. Globals por módulo

| Módulo | Usa globals |
|--------|-------------|
| `app.js` | sólo ensambla; los bootstraps exponen los globals |
| `session-context.js` | `sessionId`, `KairosUtils` |
| `debug.js` | `KairosUtils`, `KairosWidgets`, `sessionId`, `debugVisible` |
| `chat-stream.js` | `sessionId`, `defaultModel`, `KairosWidgets`, `KairosForm`, `KairosMarkdown` |
| `utils.js` | — (raíz) |
| `markdown-renderer.js` | `KairosWidgets`, `marked`, `DOMPurify` |
| `stream-dispatcher.js` | `logger.js` (logStream, logUI) |
| `stream-orchestrator.js` | `logger.js`, `RetryHandler`, `StreamErrorHandler`, `KairosStream`, `KairosUtils`, `refreshSidebar`, `refreshDebug` |
| `stream-fetcher.js` | `KairosStream`, `logger.js` |
| `stream-lifecycle.js` | `KairosStream`, `logger.js` |
| `stream-retry-coordinator.js` | `RetryHandler`, `StreamErrorHandler`, `KairosUtils` |
| `chat-form.js` | `sessionId`, `defaultModel`, `KairosUtils`, `StreamOrchestrator`, `RetryHandler` |
| `retry-handler.js` | `KairosUtils`, `logger.js` |
| `stream-error-handler.js` | `KairosUtils`, `logger.js` |
| `content-handler.js` | `KairosStream`, `KairosMarkdown`, `KairosWidgets`, `KairosUtils`, `DOMPurify`, `logger.js` |
| `content-renderer.js` | `KairosMarkdown`, `KairosWidgets`, `KairosUtils` |
| `reasoning-handler.js` | `KairosStream`, `logger.js` |
| `reasoning-state.js` | (ninguno) |
| `shared-state.js` | (ninguno) |
| `dom-contracts.js` | (ninguno) |
| `logger.js` | — (raíz del logging) |
| `asr-mic.js` | `sessionId`, `KairosUtils` |
| `widget-container-renderer.js` | `KairosWidgets`, `KairosUtils` |
| `tool-call-renderer.js` | `KairosStream`, `KairosUtils`, `logger.js` |

**Observación**: `logStream`, `logUI`, `sessionId`, `defaultModel` se usan sin import — dependen de que el bundle exponga las compatibilidades históricas.

**Nota de ubicación**: `app.js`, `chat-stream.js`, `debug.js` están en la raíz de `web/static/`, no en `web/static/modules/`. El resto de módulos están en `web/static/modules/`.

## 6. Lo que está bien

- **Separación clara de responsabilidades**: fetch, dispatch, render, retry, error — cada uno su módulo.
- **Event bus simple y efectivo**: 5 eventos cubren todo el protocolo SSE.
- **Retry con backoff exponencial** (2s, 4s, 6s) y distinción auth/rate_limit vs errores recuperables.
- **State compartido explícito** en vez de globals — el `state` viaja como parámetro.
- **DOMPurify** para sanitización de HTML renderizado.
- **Debug panel** potente: logs de stream/UI/widgets, inspección de razonamiento y system prompt.
- **Compatibilidad HTML inline**: ya no es parte del flujo normal; quedaron sólo globals/bootstraps de transición.

## 7. Lo que podría mejorar

- **Globals implícitos**: `logStream`, `logUI`, `sessionId` se usan sin import. Si algún módulo se carga solo, falla silenciosamente. Deberían importarse explícitamente.
- **`content-handler.js` re-renderiza markdown en cada token** (con cache `rawText`). En respuestas largas, el coste acumulado puede ser significativo. Un debounce o throttling ayudaría.
- **`stream-renderer.js` fue eliminado**: su lógica se distribuyó en `content-handler.js`, `reasoning-handler.js`, `tool-call-renderer.js`.
- **Nombres inconsistentes**: `KairosStream` (dispatcher), `KairosForm`, `KairosMarkdown` vs `StreamOrchestrator`, `StreamErrorHandler` — mitad con prefijo `Kairos`, mitad sin él.
- **`chat-form.js`** tiene acoplamiento directo al DOM (`document.getElementById`). Podría inyectarse el DOM o usar un patrón más desacoplado.
- **Retry state es singleton global**: si el usuario abriera múltiples chats (futuro), los reintentos colisionarían.
- **No hay `AbortController` propagado al retry**: el `scheduleRetry` hace `form.dispatchEvent('submit')` que crea un nuevo controller, pero el anterior no se limpia explícitamente.
- **Event bus sin `off` automático**: los handlers se registran al importar el módulo y nunca se desregistran. En HMR o SPA navigation prolongada podría acumular listeners.
