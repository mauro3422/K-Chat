> ⚠️ This document may lag behind the current version. See [docs/ARCHITECTURE.md](ARCHITECTURE.md) and [docs/MODULES.md](MODULES.md) for the latest.

# Arquitectura Frontend — K-Chat

## 1. Qué hace cada módulo

| Módulo | Rol |
|--------|------|
| `app.js` | Entry point del bundle. Ensambla el runtime y pasa deps explícitas a las superficies de transición. |
| `session-context.js` | CRUD de sesiones, sidebar refresh y binding del selector de modelo via HTMX + fetch. |
| `debug-panel.js` | Panel de debug. Es una superficie de transición para compatibilidad y render del panel. |
| `session-page.js` | Navegación de sesión, sidebar refresh y carga de sesiones. Superficie de transición. |
| `utils.js` | Utilidades globales: `escHtml`, `scrollToBottom`, `showToast`, handlers de error global. |
| `markdown-renderer.js` | Renderiza Markdown vía `marked` + `DOMPurify`, detecta/extrae widgets HTML inline, maneja footnotes. |
| **`stream-dispatcher.js`** | **Event bus central**: `on/emit/off` para eventos `content`, `reasoning`, `tool_call`, `error`, `heartbeat`. |
| `stream-orchestrator.js` | Orquesta un stream completo: crea `errorHandler`, timeout, llama `executeStreamFetch`, maneja retry final y limpieza. |
| `stream-fetcher.js` | Ejecuta `fetch` POST al backend, lee el stream SSE línea a línea, emite eventos al dispatcher. |
| `stream-lifecycle.js` | Maneja el ciclo de vida del stream: inicio, heartbeats, fin, limpieza. |
| `stream-retry-coordinator.js` | Intermediario entre orchestrator y retry-handler: decide si reintentar y delega a `scheduleRetry`. |
| `chat-form.js` | Captura submit del form, crea DOM del mensaje usuario/asistente, dispara `StreamOrchestrator.startStream`. |
| `retry-handler.js` | Estado de reintentos: count, max (3), delay backoff (2s * intento), `shouldRetry`, `scheduleRetry`. |
| `stream-error-handler.js` | Crea closures para capturar errores del stream, marca pills de tool como error, muestra card de reintento. |
| `content-handler.js` | Listener de `content`: acumula tokens, detecta widgets (`html-widget`/`[Widget:]`), re-renderiza markdown por fase. |
| `reasoning-handler.js` | Listener de `reasoning`: crea `<details>` colapsable por fase de razonamiento, acumula tokens. |
| `reasoning-state.js` | Estado compartido de razonamiento entre fases. |
| `tool-call-renderer.js` | Listener de `tool_call`: renderiza pills de herramientas (calling → ok/error) agrupadas por fase. |
| `dom-contracts.js` | Contratos DOM para elementos del chat. |
| `logger.js` | Logging de UI y stream para el panel de debug. |
| `asr/contract.js` | Contrato compartido de telemetría, texto visible y config de ASR. |
| `asr/transcript-utils.js` | Merge, puntuación y utilidades de tokens para ASR. |
| `asr-mic.js` | Captura de micrófono, VAD, chunking, transporte y reveal progresivo. |
| `widget-container-renderer.js` | Renderizado de contenedores de widgets. |
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
stream-dispatcher.js       ← emit(msg.t, msg.d, state)
     │
     ├─→ reasoning-handler  ← crea <details class="reasoning">, append token
     ├─→ content-handler    ← acumula token en el estado del stream,
     │                       detecta widgets, parsea markdown, sanitiza con DOMPurify
     ├─→ tool-call-renderer ← renderiza pills calling/ok/error por tool
     ├─→ stream-error-handler ← captura errores type+message
     └─→ stream-lifecycle    ← maneja heartbeat/end/timeout
```

**State del stream**:
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
| `app.js` | sólo ensambla; inyecta deps explícitas en las superficies de transición |
| `session-context.js` | `KairosUtils` |
| `debug-panel.js` | `KairosDebugPanel`, `KairosWidgets`, `debugVisible` |
| `session-page.js` | `KairosWidgets`, `KairosForm`, `KairosMarkdown` |
| `utils.js` | — (raíz) |
| `markdown-renderer.js` | `KairosWidgets`, `marked`, `DOMPurify` |
| `stream-dispatcher.js` | `logger.js` (logStream, logUI) |
| `stream-orchestrator.js` | `logger.js`, `RetryHandler`, `StreamErrorHandler`, `KairosStream`, `KairosUtils`, `refreshSidebar`, `refreshDebug` |
| `stream-fetcher.js` | `KairosStream`, `logger.js` |
| `stream-lifecycle.js` | `KairosStream`, `logger.js` |
| `stream-retry-coordinator.js` | `RetryHandler`, `StreamErrorHandler`, `KairosUtils` |
| `chat-form.js` | `KairosUtils`, `StreamOrchestrator`, `RetryHandler` |
| `retry-handler.js` | `KairosUtils`, `logger.js` |
| `stream-error-handler.js` | `KairosUtils`, `logger.js` |
| `content-handler.js` | `KairosStream`, `KairosMarkdown`, `KairosWidgets`, `KairosUtils`, `DOMPurify`, `logger.js` |
| `reasoning-handler.js` | `KairosStream`, `logger.js` |
| `reasoning-state.js` | (ninguno) |
| `dom-contracts.js` | (ninguno) |
| `logger.js` | — (raíz del logging) |
| `asr-mic.js` | `KairosUtils` |
| `widget-container-renderer.js` | `KairosWidgets`, `KairosUtils` |
| `tool-call-renderer.js` | `KairosStream`, `KairosUtils`, `logger.js` |

**Observación**: `logStream`, `logUI` y las dependencias de navegación/sesión ya se inyectan desde `app.js` o se importan explícitamente; los bootstraps históricos ya no son el camino normal.

**Nota de ubicación**: `app.js` está en la raíz de `web/static/`; el resto de módulos están en `web/static/modules/`.

## 6. Lo que está bien

- **Separación clara de responsabilidades**: fetch, dispatch, render, retry, error — cada uno su módulo.
- **Event bus simple y efectivo**: 5 eventos cubren todo el protocolo SSE.
- **Retry con backoff exponencial** (2s, 4s, 6s) y distinción auth/rate_limit vs errores recuperables.
- **State compartido explícito** en vez de globals — el `state` viaja como parámetro.
- **DOMPurify** para sanitización de HTML renderizado.
- **Debug panel** potente: logs de stream/UI/widgets, inspección de razonamiento y system prompt.
- **Compatibilidad HTML inline**: ya no es parte del flujo normal; quedó acotada a superficies de transición.

## 7. Lo que podría mejorar

- **Globals implícitos**: el riesgo real ya no está en el runtime principal, sino en las superficies de transición. Si esas superficies crecen otra vez, conviene volver a inyectar deps explícitas.
- **`content-handler.js` re-renderiza markdown en cada token** (con cache `rawText`). En respuestas largas, el coste acumulado puede ser significativo. Un debounce o throttling ayudaría.
- **`stream-renderer.js` fue eliminado**: su lógica se distribuyó en `content-handler.js`, `reasoning-handler.js`, `tool-call-renderer.js`.
- **Nombres inconsistentes**: `KairosStream` (dispatcher), `KairosForm`, `KairosMarkdown` vs `StreamOrchestrator`, `StreamErrorHandler` — mitad con prefijo `Kairos`, mitad sin él.
- **`chat-form.js`** todavía tiene acoplamiento directo al DOM porque es una superficie de transición.
- **Retry state es singleton global**: si el usuario abriera múltiples chats (futuro), los reintentos colisionarían.
- **No hay `AbortController` propagado al retry**: el `scheduleRetry` hace `form.dispatchEvent('submit')` que crea un nuevo controller, pero el anterior no se limpia explícitamente.
- **Event bus sin `off` automático**: los handlers se registran al importar el módulo y nunca se desregistran. En HMR o SPA navigation prolongada podría acumular listeners.
