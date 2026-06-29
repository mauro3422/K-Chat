> ⚠️ **DEPRECATED** — Este documento describe la arquitectura frontend pre-migración a TypeScript (v0.0.64). Ya no refleja el estado real del sistema. El frontend vivo es TypeScript con Vite build, ver:
> - [`docs/ARCHITECTURE_FRONTEND_TS.md`](ARCHITECTURE_FRONTEND_TS.md) — arquitectura TS actual
> - [`docs/ARCHITECTURE.md`](ARCHITECTURE.md) — overview arquitectónico
> - [`docs/MODULES.md`](MODULES.md) — inventario de módulos
>
> Conservado solo como referencia histórica. No actualizar. **No confiar en este doc para decisiones técnicas actuales.**
>
> **Last updated:** 2026-06-14 — Full module inventory + ASR subsystem + widgets subsystem (pre-TS migration).

# Arquitectura Frontend — K-Chat

## 1. Qué hace cada módulo

### Módulos raíz (`web/static/`)

| Módulo | Rol |
|--------|------|
| `app.js` | Entry point del bundle. Ensambla el runtime, inyecta dependencias explícitas a las superficies de transición. |
| `model-availability.js` | IIFE que fetches `/models/availability` y pinta dots de estado por modelo. |

### Módulos principales (`web/src_ts/` y compatibilidad servida en `web/static/`)

| Módulo | Rol |
|--------|------|
| `api-client.js` | ApiClient singleton. Fetch unificado con manejo de errores, timeouts y retry. |
| `session-context.js` | CRUD de sesiones, sidebar refresh y binding del selector de modelo via HTMX + fetch. |
| `core/DebugManager.ts` | Panel de debug. Superficie de transición para compatibilidad y render del panel. |
| `core/SessionList.ts` / `core/ui/ChatForm.ts` | Navegación de sesión, sidebar refresh y carga de sesiones. Superficie de transición. |
| `utils.js` | Utilidades globales: `escHtml`, `scrollToBottom`, `showToast`, handlers de error global. |
| `rendering/DomRenderer.ts` | Renderiza Markdown vía `marked` + `DOMPurify`, detecta/extrae widgets HTML inline, maneja footnotes. |
| `message-renderer.js` | `renderMessageList`, renderizado dinámico de mensajes. |
| `sidebar-refresh.js` | `refreshSidebar`, función compartida entre módulos para refrescar la barra lateral. |
| `stream-completion.js` | `handleSuccessfulStream`, extraído del orchestrator para manejo post-stream. |
| `file-attachment.js` | `FileAttachment`, input de archivos + drag&drop + paste. |
| `core/RateLimitCooldown.ts` | `RateLimitCooldown`, deshabilita input durante cooldown post-429. |
| `skills-ui.ts` | `SkillsUI` (único TypeScript), catálogo de skills + modal. |
| **`stream-dispatcher.js`** | **Event bus central**: `on/emit/off` para eventos `content`, `reasoning`, `tool_call`, `error`, `heartbeat`. |
| `streaming/StreamOrchestrator.ts` | Orquesta un stream completo: crea `errorHandler`, timeout, llama `executeStreamFetch`, maneja retry final y limpieza. |
| `stream-fetcher.js` | Ejecuta `fetch` POST al backend, lee el stream NDJSON línea a línea, emite eventos al dispatcher. |
| `stream-lifecycle.js` | Maneja el ciclo de vida del stream: inicio, heartbeats, fin, limpieza. |
| `stream-retry-coordinator.js` | Intermediario entre orchestrator y retry-handler: decide si reintentar y delega a `scheduleRetry`. |
| `core/ChatForm.ts` | Captura submit del form, crea DOM del mensaje usuario/asistente, dispara `StreamOrchestrator.startStream`. |
| `core/RetryHandler.ts` | Estado de reintentos: count, max (3), delay backoff (2s * intento), `shouldRetry`, `scheduleRetry`. |
| `streaming/error-renderer.ts` | Crea closures para capturar errores del stream, marca pills de tool como error, muestra card de reintento. |
| `streaming/ContentHandler.ts` | Listener de `content`: acumula tokens, detecta widgets (`html-widget`/`[Widget:]`), re-renderiza markdown por fase. |
| `streaming/reasoning-handler.ts` | Listener de `reasoning`: crea `<details>` colapsable por fase de razonamiento, acumula tokens. |
| `reasoning-state.js` | Estado compartido de razonamiento entre fases. |
| `streaming/tool-call-renderer.ts` | Listener de `tool_call`: renderiza pills de herramientas (calling → ok/error) agrupadas por fase. |
| `dom-contracts.js` | Contratos DOM para elementos del chat. |
| `logger.js` | Logging de UI y stream para el panel de debug. |
| `log-ui.js` | Logging de eventos UI para el panel de debug. |
| `stream-context.js` | Gestión del contexto del stream (sesión, modelo, estado). |
| `stream-contract.js` | Contratos de eventos y tipos del protocolo NDJSON. |
| `rendering/WidgetContainerRenderer.ts` | Renderizado de contenedores de widgets. |
| `asr-mic.js` | Captura de micrófono, VAD, chunking, transporte y reveal progresivo. |

### Submódulos ASR (`web/static/modules/asr/`)

| Módulo | Rol |
|--------|------|
| `contract.js` | Contrato compartido de telemetría, texto visible y config de ASR. |
| `transcript-utils.js` | Merge, puntuación y utilidades de tokens para ASR. |
| `audio-capture.js` | AudioCapture: micrófono → AudioWorklet → PCM. |
| `vad.js` | VadSegmenter: segmentación de habla (voice activity detection). |
| `pcm-utils.js` | `mergeFloat32Chunks`, `encodeWav` — utilidades de formato PCM. |
| `transcription-transport.js` | AsrTranscriptionTransport: transporte vía WebSocket + HTTP. |
| `pcm-worklet.js` | AsrPcmProcessor: AudioWorkletProcessor para captura PCM. |

### Submódulos Widgets (`web/static/modules/widgets/`)

| Módulo | Rol |
|--------|------|
| `canvas-workspace.ts` | CanvasWorkspace (TypeScript): dashboard drag&drop de widgets. |

---

## 2. Sistema de streaming: Flujo token → DOM

```
[Backend NDJSON]
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

---

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

---

## 4. Event bus (`stream-dispatcher.js`)

```js
StreamDispatcher.on('content', (token, state) => { ... });
StreamDispatcher.emit('content', token, state);
StreamDispatcher.off('content', callback);
```

- **Eventos**: `reasoning`, `content`, `tool_call`, `error`, `heartbeat`
- **Patrón**: Pub/sub síncrono, listeners en array, try/catch individual por listener
- **Registros default** en el dispatcher: `logStream()` y `logUI()` para debug

---

## 5. Globals por módulo

| Módulo | Usa globals |
|--------|-------------|
| `app.js` | sólo ensambla; inyecta deps explícitas en las superficies de transición |
| `api-client.js` | — (singleton autocontenido) |
| `model-availability.js` | — (IIFE autocontenida) |
| `session-context.js` | `KairosUtils` |
| `core/DebugManager.ts` | `KairosDebugPanel`, `KairosWidgets`, `debugVisible` |
| `core/SessionList.ts` / `core/ui/ChatForm.ts` | `KairosWidgets`, `KairosForm`, `KairosMarkdown` |
| `utils.js` | — (raíz) |
| `rendering/DomRenderer.ts` | `KairosWidgets`, `marked`, `DOMPurify` |
| `message-renderer.js` | `KairosUtils`, `KairosMarkdown` |
| `sidebar-refresh.js` | `KairosUtils` |
| `stream-completion.js` | `KairosUtils`, `refreshSidebar`, `refreshDebug` |
| `file-attachment.js` | `KairosUtils` |
| `core/RateLimitCooldown.ts` | — (autocontenido, escucha eventos HTMX) |
| `skills-ui.ts` | — (autocontenido, fetch + render modal) |
| `stream-dispatcher.js` | `logger.js` (logStream, logUI) |
| `streaming/StreamOrchestrator.ts` | `logger.js`, `RetryHandler`, `StreamErrorHandler`, `StreamDispatcher`, `KairosUtils`, `refreshSidebar`, `refreshDebug` |
| `stream-fetcher.js` | `StreamDispatcher`, `logger.js` |
| `stream-lifecycle.js` | `StreamDispatcher`, `logger.js` |
| `stream-retry-coordinator.js` | `RetryHandler`, `StreamErrorHandler`, `KairosUtils` |
| `core/ChatForm.ts` | `KairosUtils`, `StreamOrchestrator`, `RetryHandler` |
| `core/RetryHandler.ts` | `KairosUtils`, `logger.js` |
| `streaming/error-renderer.ts` | `KairosUtils`, `logger.js` |
| `streaming/ContentHandler.ts` | `StreamDispatcher`, `KairosMarkdown`, `KairosWidgets`, `KairosUtils`, `DOMPurify`, `logger.js` |
| `streaming/reasoning-handler.ts` | `StreamDispatcher`, `logger.js` |
| `reasoning-state.js` | (ninguno) |
| `dom-contracts.js` | (ninguno) |
| `logger.js` | — (raíz del logging) |
| `log-ui.js` | — (raíz del logging UI) |
| `stream-context.js` | `StreamDispatcher` |
| `stream-contract.js` | (ninguno) |
| `rendering/WidgetContainerRenderer.ts` | `KairosWidgets`, `KairosUtils` |
| `asr-mic.js` | `KairosUtils` |
| `streaming/tool-call-renderer.ts` | `StreamDispatcher`, `KairosUtils`, `logger.js` |

**Observación**: `logStream`, `logUI` y las dependencias de navegación/sesión ya se inyectan desde `app.js` o se importan explícitamente; los bootstraps históricos ya no son el camino normal.

**Nota de ubicación**: `app.js` y `model-availability.js` están en `web/static/`; la implementación viva del frontend está en `web/src_ts/`. Los módulos históricos que siguen servidos para transición quedan acotados en `web/static/modules/`. Los submódulos ASR siguen en `web/static/modules/asr/` y los de widgets en `web/static/modules/widgets/`.

---

## 6. Lo que está bien

- **Separación clara de responsabilidades**: fetch, dispatch, render, retry, error — cada uno su módulo.
- **Event bus simple y efectivo**: 5 eventos cubren todo el protocolo NDJSON.
- **Retry con backoff exponencial** (2s, 4s, 6s) y distinción auth/rate_limit vs errores recuperables.
- **State compartido explícito** en vez de globals — el `state` viaja como parámetro.
- **DOMPurify** para sanitización de HTML renderizado.
- **Debug panel** potente: logs de stream/UI/widgets, inspección de razonamiento y system prompt.
- **Compatibilidad HTML inline**: ya no es parte del flujo normal; quedó acotada a superficies de transición.

---

## 7. Lo que podría mejorar

- **Globals implícitos**: el riesgo real ya no está en el runtime principal, sino en las superficies de transición. Si esas superficies crecen otra vez, conviene volver a inyectar deps explícitas.
- **`ContentHandler.ts` re-renderiza markdown en cada token** (con cache `rawText`). En respuestas largas, el coste acumulado puede ser significativo. Un debounce o throttling ayudaría.
- **`stream-renderer.js` fue eliminado**: su lógica se distribuyó en `ContentHandler.ts`, `reasoning-handler.ts`, `tool-call-renderer.ts`.
- **Nombres inconsistentes**: `KairosStream`/`StreamDispatcher`, `KairosForm`, `KairosMarkdown` vs `StreamOrchestrator`, `StreamErrorHandler` — mitad con prefijo `Kairos`, mitad sin él.
- **`core/ChatForm.ts`** todavía tiene acoplamiento directo al DOM porque es una superficie de transición.
- **Retry state es singleton global**: si el usuario abriera múltiples chats (futuro), los reintentos colisionarían.
- **No hay `AbortController` propagado al retry**: el `scheduleRetry` hace `form.dispatchEvent('submit')` que crea un nuevo controller, pero el anterior no se limpia explícitamente.
- **Event bus sin `off` automático**: los handlers se registran al importar el módulo y nunca se desregistran. En HMR o SPA navigation prolongada podría acumular listeners.

(End of file)
