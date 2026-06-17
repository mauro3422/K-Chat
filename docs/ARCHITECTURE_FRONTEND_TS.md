# Arquitectura Frontend TypeScript — K-Chat

> **Última actualización:** 2026-06-16
> **Versión:** TS Prototype (refactor completo)
> **Entry point:** `web/src_ts/app_mock.ts`
> **Build output:** `web/static/dist/assets/app_mock.js`

---

## Tabla de Contenidos

1. [Filosofía: Arquitectura Lego](#1-filosofía-arquitectura-lego)
2. [Estructura de Capas](#2-estructura-de-capas)
3. [Composition Root (app_mock.ts)](#3-composition-root)
4. [Core — Infraestructura](#4-core--infraestructura)
5. [Core — Sesión y UI](#5-core--sesión-y-ui)
6. [Core — Notificaciones](#6-core--notificaciones)
7. [Rendering](#7-rendering)
8. [Streaming](#8-streaming)
9. [Widgets](#9-widgets)
10. [Layout Grid + Efectos](#10-layout-grid--efectos)
11. [Sistema de Tipos (types/)](#11-sistema-de-tipos)
12. [DOM Contracts](#12-dom-contracts)
13. [Event Bus](#13-event-bus)
14. [Streaming Pipeline](#14-streaming-pipeline)
15. [Pruebas](#15-pruebas)
16. [Build y Bundling](#16-build-y-bundling)
17. [Roadmap](#17-roadmap)

---

## 1. Filosofía: Arquitectura Lego

Cada pieza del sistema es un **bloque independiente** que:

1. **Declara una interfaz** (`I*`) en `types/`
2. **Implementa** la interfaz en su archivo
3. **Recibe sus dependencias** por constructor (Dependency Injection)
4. **Se comunica** via EventBus o callbacks
5. **No sabe nada** de capas superiores

```
  types/  ←── core/  ←── rendering/  ←── streaming/  ←── widgets/  ←── app_mock.ts
  (hoja)     (lógica)     (DOM)           (eventos)       (componentes)  (wiring)
```

**Regla de oro:** Las dependencias fluyen en UNA dirección. Una capa inferior nunca importa de una superior.

---

## 2. Estructura de Capas

```
web/src_ts/
├── types/            # Interfaces y tipos (37 interfaces I*, ~15 tipos de datos)
│   ├── api.ts
│   ├── chat-form.ts
│   ├── debug.ts
│   ├── dispatcher.ts
│   ├── events.ts         ← IEventBus, EventCallback
│   ├── iframe.ts
│   ├── layout.ts         ← ILayoutGrid, ICanvasOverlay, ICSSInjector, IAudioBus
│   ├── message-view.ts
│   ├── rendering.ts
│   ├── sse.ts
│   ├── streaming.ts
│   ├── widget-renderer.ts
│   └── widgets.ts
│
├── core/              # Lógica de negocio pura (sin DOM directo)
│   ├── infra/             # Infraestructura base
│   │   ├── DomContracts.ts   ← 27 constantes de clases CSS
│   │   ├── EventBus.ts       ← TypedEventBus
│   │   ├── Logger.ts         ← ILogger
│   │   ├── LoggerFactory.ts  ← getLogger()
│   │   └── CSSInjector.ts    ← ICSSInjector (NUEVO)
│   ├── session/
│   │   ├── SessionStore.ts   ← ISessionStore
│   │   └── SessionList.ts    ← ISessionList
│   ├── notification/
│   │   ├── NotificationService.ts
│   │   ├── NotificationBell.ts
│   │   ├── RateLimitCooldown.ts
│   │   ├── ToastUI.ts
│   │   └── AudioBus.ts       ← IAudioBus (NUEVO)
│   ├── ui/
│   │   ├── ChatForm.ts
│   │   ├── FileUploader.ts
│   │   ├── RetryHandler.ts
│   │   └── GridController.ts ← ILayoutGrid (NUEVO)
│   ├── debug/
│   │   ├── DebugManager.ts
│   │   └── DomTreeSerializer.ts
│   └── widget/
│       ├── WidgetRegistry.ts
│       ├── WidgetDetector.ts
│       └── WidgetStateManager.ts
│
├── rendering/         # Manipulación del DOM
│   ├── MessageView.ts           ← IMessageView
│   ├── DomRenderer.ts           ← IDomRenderer
│   ├── IframeBuilder.ts         ← IIframeBuilder
│   └── WidgetContainerRenderer.ts ← IWidgetContainerRenderer
│
├── streaming/         # Streaming NDJSON + SSE
│   ├── StreamOrchestrator.ts    ← IStreamOrchestrator
│   ├── NDJSONStreamClient.ts    ← INDJSONStreamClient
│   ├── SSEClient.ts             ← ISSEClient
│   ├── StreamDispatcher.ts      ← IStreamDispatcher
│   ├── StreamSimulator.ts       ← IStreamSimulator
│   ├── ContentHandler.ts        ← IContentHandler
│   ├── tool-call-renderer.ts
│   ├── error-renderer.ts
│   └── reasoning-handler.ts
│
├── widgets/           # Componentes visuales complejos
│   ├── CanvasWorkspace.ts       ← ICanvasWorkspace
│   ├── CanvasCardManager.ts     ← ICanvasCardManager
│   ├── CanvasLayoutStore.ts     ← ILayoutStore
│   ├── CanvasOverlay.ts         ← ICanvasOverlay (NUEVO)
│   ├── SkillsUI.ts              ← ISkillsUI
│   └── templates.ts
│
├── api/
│   └── ApiClient.ts             ← IChatApi, ISessionApi, etc.
│
└── app_mock.ts        ← Composition Root (wiring de todos los bloques)
```

---

## 3. Composition Root (`app_mock.ts`)

Único archivo que **instancia todo** con `new`. Cero lógica de negocio.

### Orden de inicialización

```
1. EventBus ────────── singleton central de comunicación
2. DebugManager ────── panel de debug
3. WidgetRegistry ──── registro de widgets
4. ApiClient ────────── comunicación con backend
5. IframeBuilder ────── construcción de iframes
6. WidgetContainerRenderer
7. CSSInjector ──────── inyección dinámica de CSS (NUEVO)
8. AudioBus ─────────── sonidos vía EventBus (NUEVO)
9. GridController ───── layout grid (NUEVO)
10. CanvasOverlay ────── canvas de efectos (NUEVO)
11. CanvasLayoutStore
12. CanvasCardManager
13. FileUploader
14. MessageView
15. ChatForm
16. SessionList
17. StreamSimulator
18. SessionStore
19. NDJSONStreamClient
20. SSEClient
21. NotificationService, RateLimitCooldown, ToastUI, NotificationBell
22. SkillsUI
23. CanvasWorkspace
24. RetryController
25. StreamOrchestrator
```

### Bloques expuestos globalmente

```typescript
(window as any).__k = {
  cssInjector,    // Inyectar/remover CSS dinámico
  audioBus,       // Reproducir sonidos
  gridController, // Manipular layout grid
  canvasOverlay,  // Efectos visuales + drawing mode
  eventBus,       // Eventos del sistema
};
```

---

## 4. Core — Infraestructura

### DomContracts.ts

Centraliza TODAS las clases CSS como constantes. 27 constantes.

```typescript
export const C = {
  MSG_BODY: 'msg-body',
  REASONING: 'reasoning',
  TOOL_CALLS: 'tool-calls',
  TC_ITEM: 'tc-item',
  WIDGET_CONTAINER: 'interactive-widget-container',
  ERROR_CARD: 'error-card',
  // ... 27 total
} as const;
```

**Regla:** Ningún archivo fuera de `DomContracts.ts` hardcodea clases CSS.

### TypedEventBus (IEventBus)

Pub/sub genérico con tipado en eventos.

```typescript
interface IEventBus {
  on<T>(event: string, callback: EventCallback<T>): void;
  off<T>(event: string, callback: EventCallback<T>): void;
  emit<T>(event: string, data: T): void;
  removeAllListeners(event?: string): void;
}
```

**Eventos del sistema:**

| Evento | Payload | Emisor | Receptor |
|--------|---------|--------|----------|
| `chat:send` | `{ text, sessionId, model }` | ChatForm | StreamOrchestrator |
| `stream:abort` | `void` | ChatForm | StreamOrchestrator |
| `session:select` | `{ sessionId }` | SessionList | SessionStore |
| `sessions:updated` | `{ sessions, activeId }` | StreamOrchestrator | SessionList |
| `notification:show` | `{ type, message }` | NotificationService | ToastUI, NotificationBell |
| `rate-limit:detected` | `{ duration }` | NDJSONStreamClient | RateLimitCooldown |
| `sse:new-message` | `MessageData` | SSEClient | MessageView |
| `audio:play` | `SoundName` | AudioBus | — |

### CSSInjector (ICSSInjector) — NUEVO

Inyecta y remueve estilos CSS dinámicamente en `<head>`.

```typescript
interface ICSSInjector {
  inject(id: string, css: string): HTMLStyleElement;
  remove(id: string): void;
  has(id: string): boolean;
  clear(): void;
}
```

**Uso:**
```typescript
cssInjector.inject('rain-bg', `
  body { background: linear-gradient(180deg, #0a0a1a, #1a1a3e); }
  .msg-body { border-radius: 20px !important; }
`);
cssInjector.remove('rain-bg');
```

### Logger (ILogger)

Logger estructurado que alimenta el panel de debug.

```typescript
interface ILogger {
  info(tag: string, ...args: unknown[]): void;
  warn(tag: string, ...args: unknown[]): void;
  error(tag: string, ...args: unknown[]): void;
  debug(tag: string, ...args: unknown[]): void;
}
```

---

## 5. Core — Sesión y UI

### SessionStore (ISessionStore)

Maneja el estado de las sesiones: activa, historial, CRUD.

```typescript
interface ISessionStore {
  readonly sessions: Array<{ id, name, count, last_str }>;
  readonly activeSessionId: string;
  readonly activeHistory: MessageData[];
  init(eventBus: IEventBus): void;
  selectSession(id: string): void;
  createSession(name?: string): string;
  deleteSession(id: string): void;
  renameSession(id: string, name: string): void;
}
```

### SessionList (ISessionList)

Renderiza la barra lateral de sesiones. Maneja:
- Sesiones activas (clase `.active`)
- Marcas de no leído (clase `.has-new`)
- Sesiones de Telegram (ícono especial)
- Renombrar/eliminar

### ChatForm (IChatForm)

Maneja el formulario de envío:
- Botón de submit
- Atajo Enter (con Shift+Enter para salto de línea)
- Estado de streaming (deshabilita durante envío)
- Selector de modelo (persistente en localStorage)

### GridController (ILayoutGrid) — NUEVO

Motor del layout grid. Trata la UI como un tablero de celdas reordenables.

```typescript
interface ILayoutGrid {
  readonly cells: ICellLayout[];
  getCell(id: string): ICellLayout | undefined;
  moveCell(id: string, area: string): void;
  updateStyle(id: string, style: Partial<CellStyle>): void;
  addCell(cell: ICellLayout): void;
  removeCell(id: string): void;
  setVariant(id: string, variant: string): void;
  setVisibility(id: string, visible: boolean): void;
  reset(): void;
  toGridTemplate(): string;
  save(): void;
  load(): void;
  on(event: 'change', cb: (cells: ICellLayout[]) => void): void;
  off(event: 'change', cb: (cells: ICellLayout[]) => void): void;
}
```

**Celdas por defecto:**
| id | Componente | Área | Visible |
|----|-----------|------|---------|
| `sidebar` | SessionList | `sidebar` | ✅ |
| `chat` | ChatArea | `chat` | ✅ |
| `canvas` | CanvasWorkspace | `canvas` | ✅ |
| `debug` | DebugPanel | `debug` | ❌ |
| `effects` | Effects | `effects` | ✅ |

---

## 6. Core — Notificaciones

### AudioBus (IAudioBus) — NUEVO

Reproduce sonidos en respuesta a eventos del sistema.

```typescript
interface IAudioBus {
  init(): void;
  play(sound: 'message' | 'error' | 'notification' | 'send' | 'connect'): void;
  setVolume(vol: number): void;
  setMuted(muted: boolean): void;
  destroy(): void;
}
```

**Mapeo de eventos a sonidos:**

| Evento | Sonido |
|--------|--------|
| `stream:content` | `message.mp3` |
| `stream:error` | `error.mp3` |
| `notification:show` | `notification.mp3` |
| `chat:send` | `send.mp3` |

### NotificationService (INotificationService)

Muestra notificaciones tipo toast con severidad (info, warning, error).

### RateLimitCooldown (IRateLimitCooldown)

Maneja el cooldown de 60s cuando se recibe un 429. Tick por segundo vía EventBus.

### NotificationBell (INotificationBell)

Campana de notificaciones en el header con badge y dropdown de historial.

---

## 7. Rendering

### MessageView (IMessageView)

Renderiza mensajes en el contenedor `#messages`.

```typescript
interface IMessageView {
  beginStreaming(role: 'user' | 'assistant'): HTMLElement;
  appendMessage(msg: MessageData): void;
  clearContainer(): void;
  renderWithWidgets: (text: string, el: HTMLElement) => void;
}
```

**Estructura de un mensaje streamed:**
```html
<div class="msg assistant live-msg streaming" data-ts="..." data-id="...">
  <div class="msg-label">Kairos</div>
  <details class="reasoning memories-phase">
    <summary>🧠 Memoria recuperada</summary>
    <div class="rt memory-content">...</div>
  </details>
  <details class="reasoning">
    <summary>🤔 Razonando...</summary>
    <div class="rt">...</div>
  </details>
  <div class="tool-calls" data-phase="0">
    <span class="tc-item calling">⚡ search_web</span>
    <span class="tc-item ok">✓ search_web</span>
  </div>
  <div class="msg-body md-content">
    <div class="interactive-widget-container" data-key="clock">
      <iframe class="widget-iframe" sandbox="allow-scripts"></iframe>
    </div>
    <div class="msg-text-segment"><p>Respuesta...</p></div>
  </div>
</div>
```

### DomRenderer (IDomRenderer)

Renderiza Markdown a HTML usando `marked` + `DOMPurify`.

### IframeBuilder (IIframeBuilder)

Crea iframes para widgets:
- `srcDoc` con HTML+CSS+JS inline
- Sandbox `allow-scripts only`
- PostMessage bridge para resize, save-state, errors
- IntersectionObserver para lazy loading

### WidgetContainerRenderer (IWidgetContainerRenderer)

Analiza el texto completo y detecta boundaries de widgets (` ```html-widget `). Solo calcula estructura, no modifica DOM.

---

## 8. Streaming

### Pipeline completo

```
Usuario escribe → ChatForm
  → EventBus.emit('chat:send')
    → StreamOrchestrator.handleChatSend()
      → NDJSONStreamClient.startStream()  (o StreamSimulator)
        → fetch POST /chat/{session_id}
          → ReadableStream (NDJSON línea por línea)
            → parseStreamEvent() {t, d}
              → StreamDispatcher.emit(t, d, context)
                → ContentHandler.handleContent()  → renderiza markdown + widgets
                → ReasoningHandler.handleReasoning() → crea <details>
                → ToolCallRenderer.handleToolCall() → crea pills
                → ErrorRenderer.handleError() → muestra error card
```

### StreamOrchestrator (IStreamOrchestrator)

Orquesta el ciclo completo de un stream:

1. **Guard** — 500ms debounce + booleano (1 stream a la vez)
2. **Timeout** — 120s, se resetea en cada chunk (incluyendo heartbeats)
3. **Retry** — hasta 3 reintentos con backoff progresivo
4. **First token** — limpia "✍️ Pensando..." del body
5. **Errores terminales** — auth, rate_limit → no reintenta
6. **Errores recuperables** — network, server → reintenta
7. **Respuesta vacía** — si tiene reasoning/tools, no reintenta
8. **Sidebar refresh** — al completar el stream
9. **Mark pills error** — en fallo terminal, marca `.calling` → `.error`

### ContentHandler (IContentHandler)

Procesa eventos `content` con optimización incremental:

```
handleContent(data):
  1. Acumula en ctx.contentTexts[phaseIndex]
  2. Procesa widgets vía containerRenderer
  3. Si NO hay nuevos boundaries de widget:
     → Camino incremental: solo actualiza último text segment
     → Salta 6/8 pasos de DOM
  4. Si HAY nuevos boundaries:
     → Camino completo: removeTextSegments + ensureWidgetContainers
       + insertTextSegments + renderTextSegments + iframeBuilder.initAll
```

### NDJSONStreamClient (INDJSONStreamClient)

Cliente real de streaming via `fetch` + `ReadableStream`.

**Manejo de errores HTTP:**
- `401` → error `auth`
- `429` → error `rate_limit` + dispara cooldown
- `500+` → error `server`
- Otros → error `http`

**Soporte de archivos:** Si `params.files` tiene elementos, usa `chatStreamWithFiles` en vez de `chatStream`.

### SSEClient (ISSEClient)

Cliente EventSource para eventos entre sesiones:
- `stream:*` → eventos de Telegram (live tokens)
- `new_message` → mensaje nuevo de otra sesión
- `session_deleted` → sesión eliminada
- `message_deleted` → mensaje eliminado

### StreamSimulator (IStreamSimulator)

Simulador para desarrollo sin backend. Genera eventos NDJSON sintéticos.

### ToolCallRenderer

Renderiza pills de herramientas:
- `calling` → ⚡ nombre (spinner)
- `ok` → ✓ nombre
- `error` → ✘ nombre
- `partial` → ignorado (igual que JS production)
- `_stream_args` → ignorado (argumentos parciales del backend)

### ErrorRenderer

Renderiza tarjetas de error:
- Error estándar (borde rojo, pulse animation)
- Rate limit (borde amarillo, icono ⏳)
- Botón de reintentar
- Marca pills como error en fallo terminal

---

## 9. Widgets

### Sistema de Widgets

Los widgets son componentes HTML+CSS+JS autocontenidos que se ejecutan en iframes sandboxed.

```
Widget ── sandbox="allow-scripts" ── iframe ── postMessage
  │                                              │
  │  HTML inline (srcDoc)                        │
  │  CSS propio                                  │  resize-iframe
  │  JS propio                                   │  save-widget-state
  │                                              │  widget-error
  └──────────────────────────────────────────────┘
```

**Contratos de postMessage:**

| Mensaje | Dirección | Propósito |
|---------|-----------|-----------|
| `resize-iframe` | Widget → App | Notificar cambio de altura |
| `save-widget-state` | Widget → App | Persistir estado |
| `widget-error` | Widget → App | Reportar error |
| `load-state` | App → Widget | Enviar estado inicial |

### CanvasWorkspace (ICanvasWorkspace)

Lienzo para widgets anclados. Los usuarios pueden "pinear" widgets del chat al canvas.

```typescript
interface ICanvasWorkspace {
  init(sessionId: string): void;
  reset(): void;
  pinWidget(containerEl: HTMLElement, widgetKey: string, code: string): void;
  isPinned(widgetKey: string): boolean;
}
```

### CanvasCardManager (ICanvasCardManager)

Maneja las tarjetas dentro del canvas:
- Arrastrar (drag) con RAF throttle
- Redimensionar
- Minimizar/restaurar
- Cerrar (desancar)
- Auto-z-index en click

### CanvasLayoutStore (ILayoutStore)

Persistencia del layout del canvas en localStorage.

### CanvasOverlay (ICanvasOverlay) — NUEVO

Canvas full-page para efectos visuales y modo dibujo.

```typescript
interface ICanvasOverlay {
  readonly canvas: HTMLCanvasElement | null;
  init(containerId?: string): void;
  startEffect(effect: 'rain' | 'particles' | 'snow' | 'fireworks' | 'none'): void;
  stopEffect(): void;
  setOpacity(opacity: number): void;
  setColor(color: string): void;
  startDrawMode(onDraw: (blocks: DrawBlock[]) => void): void;
  stopDrawMode(): void;
  clear(): void;
  resize(): void;
  destroy(): void;
}
```

**Efectos disponibles:**
- `rain`: 150 gotas con viento, rebote al llegar al borde
- `snow`: 100 copos con deriva aleatoria
- `particles`: 50 partículas coloridas con ciclo de vida
- `fireworks`: Explosiones cada ~1s con gravedad

**Drawing mode:** El usuario dibuja rectángulos en el canvas. La IA recibe `DrawBlock[]` con coordenadas y tipo.

---

## 10. Layout Grid + Efectos

### Sistema Grid

El layout se basa en CSS Grid, manejado dinámicamente por `GridController`.

```html
<div id="app" class="grid-layout" style="grid-template-areas: 'sidebar chat canvas'">
  <aside id="sidebar">...</aside>
  <main id="main">...</main>
  <div id="canvas-workspace">...</div>
  <div id="debug-panel">...</div>
</div>
```

**CSS:**
```css
#app.grid-layout {
  display: grid;
  grid-template-areas: "sidebar  chat     canvas"
                       "sidebar  chat     canvas"
                       "effects  toolbar  debug";
  grid-template-columns: 260px 1fr 300px;
}
```

### Capas visuales (z-index stacking)

```
z-index: 9999   →  Canvas overlay (efectos, drawing mode)
z-index: 100    →  Debug panel, notificaciones
z-index: 10     →  Canvas workspace, sidebar
z-index: 1      →  Main content (chat)
z-index: -1     →  bg-effects slot
```

### HTML Slots

```html
<body>
  <canvas id="fx-canvas" class="fx-canvas"></canvas>  <!-- Efectos full-page -->
  <div id="bg-effects" class="bg-effects"></div>       <!-- Fondos animados -->
  <div id="app">
    <!-- layout normal -->
  </div>
</body>
```

---

## 11. Sistema de Tipos (`types/`)

Capa más baja del sistema. No importa nada del proyecto.

### Interfaces de Servicio (37 total)

| Interfaz | Archivo | Implementación |
|----------|---------|----------------|
| `IEventBus` | `events.ts` | `TypedEventBus` |
| `ILogger` | — | `Logger` |
| `IMessageView` | `message-view.ts` | `MessageView` |
| `IChatForm` | `chat-form.ts` | `ChatForm` |
| `ISessionStore` | — | `SessionStore` |
| `ISessionList` | — | `SessionList` |
| `IDebugManager` | `debug.ts` | `DebugManager` |
| `IRetryController` | — | `RetryController` |
| `IStreamDispatcher<T>` | `dispatcher.ts` | `StreamDispatcher` |
| `INDJSONStreamClient` | — | `NDJSONStreamClient` |
| `ISSEClient` | `sse.ts` | `SSEClient` |
| `IStreamOrchestrator` | — | `StreamOrchestrator` |
| `IStreamSimulator` | — | `StreamSimulator` |
| `IContentHandler` | — | `ContentHandler` |
| `IWidgetRegistry` | `widgets.ts` | `WidgetRegistry` |
| `IWidgetStateManager` | `widgets.ts` | `WidgetStateManager` |
| `IWidgetController` | `widgets.ts` | — |
| `IWidgetIframeBuilder` | `widgets.ts` | `IframeBuilder` |
| `IWidgetContainerRenderer` | `widget-renderer.ts` | `WidgetContainerRenderer` |
| `IIframeBuilder` | `iframe.ts` | `IframeBuilder` |
| `ICanvasWorkspace` | — | `CanvasWorkspace` |
| `ICanvasCardManager` | `widgets.ts` | `CanvasCardManager` |
| `ILayoutStore` | `widgets.ts` | `CanvasLayoutStore` |
| `ISkillsUI` | — | `SkillsUI` |
| `INotificationService` | — | `NotificationService` |
| `INotificationBell` | — | `NotificationBell` |
| `IRateLimitCooldown` | — | `RateLimitCooldown` |
| `IFileUploader` | — | `FileUploader` |
| `IDomRenderer` | `rendering.ts` | `DomRenderer` |
| `ILayoutGrid` | `layout.ts` | `GridController` |
| `ICanvasOverlay` | `layout.ts` | `CanvasOverlay` |
| `ICSSInjector` | `layout.ts` | `CSSInjector` |
| `IAudioBus` | `layout.ts` | `AudioBus` |
| `IChatApi` | `api.ts` | `ApiClient` |
| `ISessionApi` | `api.ts` | `ApiClient` |
| `IWidgetApi` | `api.ts` | `ApiClient` |
| `IDebugApi` | `api.ts` | `ApiClient` |

---

## 12. DOM Contracts

Centralizados en `DomContracts.ts`. 27 constantes.

```typescript
export const C = {
  // Messages
  MSG_BODY: 'msg-body',
  MD_CONTENT: 'md-content',
  MSG_TEXT_SEGMENT: 'msg-text-segment',
  LIVE_MSG: 'live-msg',

  // Reasoning
  REASONING: 'reasoning',
  REASONING_MEMORIES: 'reasoning memories-phase',
  RT: 'rt',
  MEMORY_CONTENT: 'rt memory-content',

  // Tool Calls
  TOOL_CALLS: 'tool-calls',
  TC_ITEM: 'tc-item',
  TC_ITEM_CALLING: 'tc-item calling',
  TC_ITEM_OK: 'tc-item ok',
  TC_ITEM_ERROR: 'tc-item error',

  // Errors
  ERROR_CARD: 'error-card',
  RATE_LIMIT_CARD: 'rate-limit-card',
  ERROR_HEADER: 'error-header',
  ERROR_DETAIL: 'error-detail',
  ERROR_HINT: 'error-hint',
  RETRY_BTN: 'error-retry-btn',

  // Widgets
  WIDGET_CONTAINER: 'interactive-widget-container',
  WIDGET_IFRAME: 'widget-iframe',
  WIDGET_PLACEHOLDER: 'widget-placeholder',
  WIDGET_LOADING: 'widget-loading',
  WIDGET_ERROR: 'widget-error',
  WIDGET_TOOLBAR: 'widget-toolbar',

  // Misc
  MSG_LABEL: 'msg-label',
  MSG_TS: 'msg-ts',
  MSG_DELETE_BTN: 'msg-delete-btn',
  EMPTY_STATE: 'empty-state',
  STREAMING: 'streaming',
} as const;
```

**Tests:** 31 tests en `dom-contracts.test.ts` verifican que cada constante tenga el valor esperado.

---

## 13. Event Bus

### TypedEventBus

Implementación genérica con tipado por evento.

```typescript
class TypedEventBus implements IEventBus {
  private listeners: Map<string, EventCallback[]>;
  private static MAX_LISTENERS = 50;  // leak protection

  on<T>(event: string, callback: EventCallback<T>): void;
  off<T>(event: string, callback: EventCallback<T>): void;
  emit<T>(event: string, data: T): void;
  removeAllListeners(event?: string): void;
}
```

### Patrón de suscripción con cleanup

Cada componente que se suscribe guarda referencias para desuscribirse:

```typescript
class Componente {
  private _boundListeners: Array<{ event: string; cb: EventCallback<any> }> = [];

  init(): void {
    const cb = (data: SomeType) => { /* handler */ };
    this.eventBus.on('event:name', cb);
    this._boundListeners.push({ event: 'event:name', cb: cb as EventCallback<any> });
  }

  destroy(): void {
    this._boundListeners.forEach(({ event, cb }) => this.eventBus.off(event, cb));
    this._boundListeners = [];
  }
}
```

---

## 14. Streaming Pipeline

### Formato NDJSON (backend)

Cada línea es JSON:
```json
{"t": "content", "d": "texto del token"}
{"t": "reasoning", "d": "pensamiento interno"}
{"t": "tool_call", "d": "{\"name\":\"search\",\"status\":\"calling\"}"}
{"t": "tool_call", "d": "{\"name\":\"search\",\"status\":\"ok\"}"}
{"t": "heartbeat", "d": ""}
{"t": "error", "d": "{\"type\":\"rate_limit\",\"message\":\"..."}
{"t": "memory", "d": "bloque de memoria recuperada"}
```

### Flujo de eventos

```
                    NDJSONStreamClient
                           │
                    parseStreamEvent(line)
                           │
                    StreamDispatcher.emit(t, d, ctx)
                           │
            ┌──────────────┼──────────────┐
            │              │              │
       ContentHandler  ReasoningHandler  ToolCallRenderer
            │              │              │
       renderMarkdown()  <details>       pills
       + widget detect   acumula texto   calling→ok→error
       + autoScroll
```

### Lifecycle del StreamOrchestrator

```
startStream(params):
  │
  ├─ Guard (500ms + boolean)
  ├─ Timeout (120s, reset en cada chunk)
  ├─ NDJSONStreamClient.startStream()
  │    ├─ Error HTTP? → emit error + return
  │    ├─ ReadStream loop:
  │    │    ├─ heartbeat → onChunk (reset timeout)
  │    │    ├─ content → dispatcher.emit
  │    │    ├─ reasoning → dispatcher.emit
  │    │    ├─ tool_call → dispatcher.emit
  │    │    └─ error → dispatcher.emit
  │    └─ Done? → return
  │
  ├─ ¿Error en stream?
  │    ├─ auth/rate_limit? → terminal, mark pills error
  │    ├─ ¿retry disponible? → scheduleRetry + return
  │    └─ no retry? → mark pills error + show error card
  │
  ├─ ¿Respuesta vacía?
  │    ├─ ¿tiene reasoning/tools? → no retry
  │    └─ vacía sin nada? → retry
  │
  └─ Success → refresh sidebar + finalize
```

---

## 15. Pruebas

### Suite de tests (96 tests, 8 archivos)

| Archivo | Tests | Qué cubre |
|---------|-------|-----------|
| `dom-contracts.test.ts` | 31 | Constantes CSS vs valores esperados |
| `message-view.test.ts` | 16 | Creación de mensajes, beginStreaming, clearContainer |
| `session-list.test.ts` | 10 | Render, active, unread, rename, delete |
| `reasoning-handler.test.ts` | 10 | Fases de reasoning, acumulación, inserción DOM |
| `tool-call-renderer.test.ts` | 6 | Pills calling→ok→error, phaseIndex, partial skip |
| `error-renderer.test.ts` | 7 | Error cards, rate-limit cards, retry button |
| `retry-controller.test.ts` | 11 | Retry count, backoff, max retries |
| `stream-dispatcher.test.ts` | 5 | Event emit/on/off |

### Configuración

```javascript
// vitest.ts.config.js
export default defineConfig({
  test: {
    environment: 'happy-dom',  // DOM simulado para tests
    include: ['web/src_ts/**/*.test.ts'],
    setupFiles: ['web/src_ts/__tests__/setup.ts'],
  },
});
```

### Ejecución

```bash
npm run test:ts                    # Todos los tests (recomendado: usa testmon)
npx vitest run --config vitest.ts.config.js web/src_ts/__tests__/message-view.test.ts
```

---

## 16. Build y Bundling

### Vite Config

```javascript
// vite.config.js
build: {
  outDir: 'dist',
  sourcemap: process.env.NODE_ENV === 'development',
  rollupOptions: {
    input: { app: 'web/static/app.js', app_mock: 'web/src_ts/app_mock.ts' },
    output: {
      manualChunks(id) {
        if (id.includes('src_ts/widgets/')) return 'widgets';
        if (id.includes('src_ts/streaming/')) return 'streaming';
        if (id.includes('src_ts/rendering/')) return 'rendering';
        if (id.includes('src_ts/core/debug') || id.includes('DebugManager')) return 'debug';
      },
    },
  },
},
```

### Chunks generados

| Chunk | Tamaño | Contenido |
|-------|--------|-----------|
| `app_mock.js` | 37 KB | Composition root + core |
| `streaming-*.js` | 51 KB | StreamOrchestrator, NDJSONClient, SSEClient, handlers |
| `rendering-*.js` | 22 KB | MessageView, DomRenderer, IframeBuilder |
| `widgets-*.js` | 20 KB | CanvasOverlay, CanvasWorkspace, SkillsUI |
| `iframe-*.js` | 14 KB | Iframe builder (compartido) |
| `debug-*.js` | 6 KB | Debug panel |
| `sse-client-*.js` | 8 KB | SSE client |
| **Total** | **~268 KB** (~75 KB gzip) |

---

## 17. Roadmap

### ✅ Completado

- [x] 39 clases, 39 interfaces (100% Lego)
- [x] Sistema de inyección de dependencias
- [x] Streaming real (NDJSON + SSE)
- [x] Widgets sandboxed con iframes
- [x] Canvas workspace con drag/resize
- [x] Panel de debug
- [x] Notificaciones + rate limit
- [x] Build optimizado (code splitting, sourcemaps condicional)
- [x] Memory leaks cerrados
- [x] ContentHandler incremental
- [x] Sistema Layout Grid (GridController)
- [x] Canvas Overlay con efectos + drawing mode
- [x] CSS Injection API
- [x] AudioBus (sonidos por eventos)
- [x] 96 tests DOM

### 🟡 Pendiente

- [ ] Conectar IA real (inyectar ndjsonClient en StreamOrchestrator)
- [ ] Visual Editor Widget (grid visual para usuarios)
- [ ] Skill de IA para manejar layout/CSS/sonidos
- [ ] View Transitions API para transiciones suaves
- [ ] Portar ASR (voz) desde JS
- [ ] Portar Widget Toolbar (editor + historial)
