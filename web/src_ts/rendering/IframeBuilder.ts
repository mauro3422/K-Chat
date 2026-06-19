import { IWidgetRegistry } from '../types/widgets';
import { fnv1a_32 } from '../core/WidgetRegistry';
import { IDebugManager } from '../types/debug';
import { IWidgetStateManager } from '../core/WidgetStateManager';
import { IIframeBuilder } from '../types/iframe';
import { C } from '../core/DomContracts';

/**
 * Widget state for lazy-loaded widget containers.
 * Maps container → { initialized, observed, widgetId }.
 */
interface WidgetState {
  initialized: boolean;
  observed: boolean;
  widgetId: string;
}

/**
 * IframeBuilder — builds sandboxed iframes with srcdoc content.
 *
 * ⚠️ HISTORY: INFINITE WIDGET GROWTH BUG (2026-06-16)
 * ─────────────────────────────────────────────────────
 * Symptom: widget grew +4px every ~35ms without stopping (4500px → 15000px+).
 * Root cause: SVG <animate repeatCount="indefinite"> + ResizeObserver w/o debounce +
 *             getDocHeight() using documentElement.scrollHeight (mirrors viewport) +
 *             +4px buffer in parent created a feedback loop.
 * Fix applied: (1) sanitizeWidgetCode() strips SVG animate/animatetransform/set,
 *             (2) getDocHeight() uses ONLY body.scrollHeight,
 *             (3) ResizeObserver has 200ms debounce,
 *             (4) +4px buffer replaced by padding-bottom:16px on body.
 *
 * ⚡ AI RULE: never generate <animate>/<animateTransform>/<set> in widgets.
 * Use CSS @keyframes instead. Sanitize removes them automatically but better
 * to not create them. See memory key: herramienta:widget-svg-animate-prohibido
 * JS reference: web/static/modules/widgets/iframe-builder.js
 *
 * Supports lazy loading: widgets are queued and only mounted when
 * the container becomes visible (via IntersectionObserver).
 *
 * Port of iframe-builder.js + iframe.js (initAll) + messaging.js
 * NOW INSTANCE-BASED: receives IWidgetRegistry via constructor.
 */
export class IframeBuilder implements IIframeBuilder {
  private debug?: IDebugManager;
  private registry: IWidgetRegistry;
  stateManager?: IWidgetStateManager;

  /** WeakMap tracking widget container state (survives DOM moves) */
  private initializedWidgets = new WeakMap<HTMLElement, WidgetState>();

  /** Global IntersectionObserver for lazy loading */
  private widgetObserver: IntersectionObserver | null = null;

  /** Debounce handle for widget resize auto-scroll */
  private _widgetScrollDebounce: number = 0;

  constructor(registry: IWidgetRegistry, debug?: IDebugManager, stateManager?: IWidgetStateManager) {
    this.registry = registry;
    this.debug = debug;
    this.stateManager = stateManager;
    // Initialize IntersectionObserver for lazy loading
    if (typeof IntersectionObserver !== 'undefined') {
      this.widgetObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            const container = entry.target as HTMLElement;
            const id = container.getAttribute('data-widget-id');
            const code = id ? this.registry.getCode(id) : undefined;
            const key = container.getAttribute('data-widget-key');
            if ((code !== undefined || key) && !container.dataset.initialized) {
              this.registry.log(id || '?', 'lazy-load', 'visible en viewport');
              this.createIframe(container, id!, code);
            }
            this.widgetObserver!.unobserve(container);
          }
        }
      }, { rootMargin: '100px' });
    }
  }

  /**
   * Strip SVG animation elements that cause infinite ResizeObserver feedback loops.
   * SVG <animate>/<animateTransform>/<set> with repeatCount="indefinite" trigger
   * continuous repaints → micro layout changes → sendHeight() never settles.
   *
   * ⚡ AI RULE: prefer CSS @keyframes over SVG animate.
   * This is a safety net for when the AI generates them anyway.
   *
   * See: web/static/modules/widgets/iframe-builder.js sanitizeWidgetCode()
   * Bug report: memoria key debug:widget-infinite-growth-fix-2026-06-16
   */
  private sanitizeWidgetCode(code: string): string {
    return code
      // Strip SVG animation tags that cause infinite growth
      .replace(/<animate\b[^>]*\/>/gi, '')
      .replace(/<animate\b[^>]*>[\s\S]*?<\/animate>/gi, '')
      .replace(/<animateTransform\b[^>]*\/>/gi, '')
      .replace(/<animateTransform\b[^>]*>[\s\S]*?<\/animateTransform>/gi, '')
      .replace(/<animateMotion\b[^>]*\/>/gi, '')
      .replace(/<animateMotion\b[^>]*>[\s\S]*?<\/animateMotion>/gi, '')
      .replace(/<set\b[^>]*\/>/gi, '')
      .replace(/<set\b[^>]*>[\s\S]*?<\/set>/gi, '');
  }

  /**
   * Build the full srcdoc HTML for a widget.
   * Includes: CSS reset, widget code, resize observer, and an explicit widget bridge.
   * Widget code is sanitized to remove SVG animations that cause infinite growth.
   */
  buildSrcDoc(id: string, code: string, initialState?: Record<string, unknown>): string {
    const stateStr = (initialState
      ? JSON.stringify(initialState)
      : '{}').replace(/<\/script/gi, '<\\/script');
    const safeCode = this.sanitizeWidgetCode(code);

    return `<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html, body {
    margin: 0;
    padding: 12px;
    overflow: hidden;
    scrollbar-width: none;
    box-sizing: border-box;
    width: 100%;
    font-family: system-ui, -apple-system, sans-serif;
    color: #c9d1d9;
    background: transparent;
  }
  *, *::before, *::after { box-sizing: inherit; }
  input, button, select, textarea { font-family: inherit; color-scheme: dark; }
  /* Safety buffer: prevent content clipping if getDocHeight is slightly off */
  .w-root { margin-bottom: 16px; }
<\/style>
<\/head>
<body>
<script>
  // ── Infra API (defined BEFORE widget code so widgets can use them) ──
  window.parent.postMessage({ type: "widget-lifecycle", id: "${id}", phase: "infra-ready" }, "*");
  window.__KAIROS_WIDGET_BRIDGE__ = {
    initialState: ${stateStr},
    saveState: function(stateObj) {
      window.parent.postMessage({
        type: "save-widget-state",
        id: "${id}",
        state: typeof stateObj === "string" ? stateObj : JSON.stringify(stateObj)
      }, "*");
    }
  };
  window.saveState = window.__KAIROS_WIDGET_BRIDGE__.saveState;

  // ── Clipboard proxy (sandboxed iframes lack secure context) ──
  // Widgets using navigator.clipboard.writeText() fail silently in null-origin
  // iframes. This proxy routes clipboard ops to the parent via postMessage.
  if (typeof navigator !== 'undefined' && navigator.clipboard) {
    var _origWrite = navigator.clipboard.writeText;
    navigator.clipboard.writeText = function(text) {
      return new Promise(function(resolve, reject) {
        try {
          window.parent.postMessage({
            type: "clipboard-write",
            id: "${id}",
            text: text
          }, "*");
          resolve();
        } catch(e) { reject(e); }
      });
    };
  }

  // ── Canvas roundRect polyfill (not in older browsers) ──
  if (!CanvasRenderingContext2D.prototype.roundRect) {
    CanvasRenderingContext2D.prototype.roundRect = function(x, y, w, h, r) {
      if (r === undefined) r = 0;
      this.moveTo(x + r, y);
      this.lineTo(x + w - r, y);
      this.quadraticCurveTo(x + w, y, x + w, y + r);
      this.lineTo(x + w, y + h - r);
      this.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
      this.lineTo(x + r, y + h);
      this.quadraticCurveTo(x, y + h, x, y + h - r);
      this.lineTo(x, y + r);
      this.quadraticCurveTo(x, y, x + r, y);
      this.closePath();
      return this;
    };
  }

  // ── Resize API ────────────────────────────────────
  function getDocHeight() {
    // ⚠️ CRITICAL: ONLY use body.scrollHeight — it's the real content height.
    // DO NOT use documentElement.scrollHeight or offsetHeight:
    // when overflow:hidden is applied, documentElement.scrollHeight MIRRORS
    // the viewport height, creating an infinite feedback loop:
    //   ResizeObserver → body.scrollHeight changes → parent resizes iframe →
    //   viewport changes → documentElement.scrollHeight changes → loop.
    // This was the root cause of the 2026-06-16 infinite growth bug.
    // See memory key: debug:widget-infinite-growth-fix-2026-06-16
    return Math.max(1, document.body.scrollHeight || 0);
  }

  var _lastSentH = -1;
  function sendHeight() {
    var h = Math.max(1, Math.round(getDocHeight()));
    if (Math.abs(h - _lastSentH) <= 2) return;
    _lastSentH = h;
    window.parent.postMessage({ type: "resize-iframe", id: "${id}", height: h }, "*");
  }

  sendHeight();
  setTimeout(sendHeight, 100);
  setTimeout(sendHeight, 600);
  setTimeout(sendHeight, 2000);

  window.addEventListener("load", function() {
    sendHeight();
    requestAnimationFrame(function() {
      requestAnimationFrame(function() {
        requestAnimationFrame(sendHeight);
      });
    });
  });

  if (window.ResizeObserver) {
    // Debounce: coalesce rapid callbacks (SVG filter recalculations, layout shifts)
    var _rsTimer = null;
    var _debouncedResize = function() {
      if (_rsTimer) clearTimeout(_rsTimer);
      _rsTimer = setTimeout(sendHeight, 200);
    };
    var _ro = new ResizeObserver(_debouncedResize);
    _ro.observe(document.documentElement);
    _ro.observe(document.body);
  }

  // No setInterval — caused infinite growth feedback loop.
  // ResizeObserver + the setTimeout calls above cover all cases, including
  // accordion expand/collapse (which fires setTimeout(sendHeight, 50) in the widget).

  // ── Widget lifecycle signal ──
  // After a brief delay, report whether the widget code executed.
  // Tracks errors between infra-ready and this signal.
  var _widgetHadError = false;
  var _origOnError = window.onerror;
  window.onerror = function(msg, url, line, col, err) {
    _widgetHadError = true;
    if (_origOnError) _origOnError(msg, url, line, col, err);
    else {
      window.parent.postMessage({
        type: "widget-error",
        id: "${id}",
        message: msg,
        line: line,
        col: col
      }, "*");
    }
  };
  setTimeout(function() {
    window.parent.postMessage({
      type: "widget-lifecycle",
      id: "${id}",
      phase: "widget-code-done",
      hadError: _widgetHadError
    }, "*");
  }, 500);
<\/script>
${safeCode}
<\/body>
<\/html>`;
  }

  /**
   * Initialize all widgets in a given scope (container element).
   * Matches production initAll() in iframe.js.
   *
   * @param parentEl - The scope element to search for widget containers
   * @param forceImmediate - Skip lazy loading and mount immediately (for historical messages)
   */
  initAll(parentEl: HTMLElement, forceImmediate = false): void {
    const scope = parentEl || document.body;
    const containers = scope.querySelectorAll('.' + C.WIDGET_CONTAINER);
    for (let i = 0; i < containers.length; i++) {
      const container = containers[i] as HTMLElement;
      const wmState = this.initializedWidgets.get(container);
      if (wmState && wmState.initialized) continue;
      if (!forceImmediate && wmState && wmState.observed) continue;

      const id = container.getAttribute('data-widget-id');
      const code = id ? this.registry.getCode(id) : undefined;
      const key = container.getAttribute('data-widget-key');
      if (code === undefined && !key) continue;

      this.registry.log(id || '?', 'init', `code=${code ? code.length : 0}b key=${key || '?'} padre=${parentEl.className || parentEl.id || '?'}`);

      if (forceImmediate || !this.widgetObserver) {
        this.createIframe(container, id!, code);
        this.initializedWidgets.set(container, { initialized: true, observed: true, widgetId: id! });
      } else {
        this.initializedWidgets.set(container, { initialized: false, observed: true, widgetId: id! });
        container.dataset.observed = '1';
        this.widgetObserver.observe(container);
        this.registry.log(id!, 'lazy-queue', 'esperando visibilidad');
      }
    }
  }

  /**
   * Create and mount an iframe into a widget container.
   * Matches production createIframe() in iframe-builder.js (without canvas-workspace pins).
   */
  private createIframe(container: HTMLElement, id: string, code?: string): void {
    if (container.dataset.initialized) return;
    container.dataset.initialized = '1';

    const key = container.getAttribute('data-widget-key');

    const wm = this.initializedWidgets;
    wm.set(container, { initialized: true, observed: true, widgetId: id });

    const hashId = key || 'widget-' + fnv1a_32(code || '');
    const savedState = this.stateManager?.getState(hashId);
    let parsedState: Record<string, unknown> | undefined;
    if (savedState) { try { parsedState = JSON.parse(savedState) as Record<string, unknown>; } catch { /* ignore */ } }

    // Show loading placeholder
    const placeholder = document.createElement('div');
    placeholder.className = C.WIDGET_PLACEHOLDER;
    const loadingNode = document.createElement('div');
    loadingNode.className = C.WIDGET_LOADING;
    loadingNode.textContent = 'Cargando widget...';
    placeholder.appendChild(loadingNode);
    container.appendChild(placeholder);

    const mountIframe = (widgetCode: string) => {
      if (placeholder && placeholder.parentNode) {
        placeholder.parentNode.removeChild(placeholder);
      }
      const iframe = document.createElement('iframe');
      iframe.className = C.WIDGET_IFRAME;
      iframe.setAttribute('sandbox', 'allow-scripts allow-modals');
      iframe.setAttribute('scrolling', 'no');
      iframe.style.width = '100%';
      iframe.style.height = '0';
      iframe.style.minHeight = '60px';
      iframe.style.border = 'none';
      iframe.style.overflow = 'hidden';
      iframe.srcdoc = this.buildSrcDoc(id, widgetCode, parsedState);
      container.appendChild(iframe);
      container.dataset.initialized = '1';
      this.debug?.logWidget(`iframe_mounted id=${id} key=${key} codeLen=${widgetCode.length}`);
    };

    if (!code && key) {
      // Tag without code — show error placeholder for now
      this.registry.log(id, 'no-code', `key=${key} sin código disponible`);
      if (placeholder.firstChild) placeholder.removeChild(placeholder.firstChild);
      const errorNode = document.createElement('div');
      errorNode.className = C.WIDGET_ERROR;
      errorNode.style.color = '#ff6b6b';
      errorNode.style.padding = '16px';
      errorNode.style.background = '#161b22';
      errorNode.style.borderRadius = '8px';
      errorNode.style.borderLeft = '3px solid #ff6b6b';
      errorNode.innerHTML = `<strong>Widget "${key}" no encontrado</strong><br><span style="color:#8b949e;font-size:13px">Este widget fue creado en una sesión anterior pero no se guardó oficialmente.</span>`;
      placeholder.appendChild(errorNode);
    } else {
      mountIframe(code!);
    }

    // Log mount info (matching production format)
    const parentScroll = container.parentElement
      ? (container.parentElement.scrollHeight > container.parentElement.clientHeight ? 'SCROLL' : 'no-scroll')
      : '?';
    this.registry.log(id, 'montado', `padre-scroll=${parentScroll} contenedor-h=${container.offsetHeight}px`);
  }

  /**
   * Handle postMessage from widget iframes.
   * Call from the main window's message event listener.
   */
  handleMessage(event: MessageEvent): void {
    const data = event.data;
    if (!data || typeof data !== 'object' || !data.type) return;

    if (event.origin !== 'null') return;

    switch (data.type) {
      case 'resize-iframe': {
        let iframe: HTMLIFrameElement | null = null;
        const container = document.querySelector(
          `.${C.WIDGET_CONTAINER}[data-widget-id="${data.id}"]`
        ) as HTMLElement | null;
        if (container) {
          iframe = container.querySelector('iframe');
        } else {
          iframe = document.querySelector(`iframe[data-widget-id="${data.id}"]`);
        }
        if (iframe) {
          iframe.style.height = data.height + 'px';
          this.registry.log(data.id, 'altura', `${data.height}px`);
          // Auto-scroll on widget expansion only if user is near bottom
          if (!this._widgetScrollDebounce) {
            this._widgetScrollDebounce = requestAnimationFrame(() => {
              this._widgetScrollDebounce = 0;
              const msgs = document.getElementById('messages');
              if (!msgs) return;
              const distFromBottom = msgs.scrollHeight - msgs.scrollTop - msgs.clientHeight;
              if (distFromBottom > 300) return;
              msgs.scrollTop = msgs.scrollHeight;
            });
          }
        }
        break;
      }

      case 'save-widget-state': {
        this.stateManager?.setState(data.id, data.state);
        this.debug?.logWidget(`state_saved id=${data.id} len=${(data.state || '').length}`);
        break;
      }

      case 'widget-error': {
        const errMsg = `[Widget ${data.id}] ${data.message} (line ${data.line}:${data.col})`;
        console.error(errMsg);
        this.debug?.logWidget(`error ${data.id} msg=${data.message} line=${data.line}`);
        break;
      }

      case 'clipboard-write': {
        // Proxy clipboard writes from sandboxed iframes (null origin can't use navigator.clipboard)
        if (data.text && navigator.clipboard) {
          navigator.clipboard.writeText(data.text).catch(() => {});
        }
        break;
      }

      case 'widget-lifecycle': {
        this.debug?.logWidget(`lifecycle id=${data.id} phase=${data.phase} hadError=${data.hadError}`);
        break;
      }
    }
  }

  /**
   * Create an iframe inside a canvas card container.
   * Unlike createIframe (private), this does not use loading placeholders
   * or .interactive-widget-container data attributes.
   */
  createCanvasIframe(container: HTMLElement, widgetKey: string, code: string): HTMLIFrameElement {
    const id = 'canvas-' + widgetKey;
    const savedState = this.stateManager?.getState(widgetKey);
    let initialState: Record<string, unknown> | undefined;
    if (savedState) { try { initialState = JSON.parse(savedState) as Record<string, unknown>; } catch { /* ignore */ } }

    const iframe = document.createElement('iframe');
    iframe.className = C.WIDGET_IFRAME;
    iframe.setAttribute('data-widget-id', id);
    iframe.setAttribute('sandbox', 'allow-scripts allow-modals');
    iframe.setAttribute('scrolling', 'no');
    iframe.style.width = '100%';
    iframe.style.height = '0';
    iframe.style.minHeight = '60px';
    iframe.style.border = 'none';
    iframe.style.overflow = 'hidden';
    iframe.srcdoc = this.buildSrcDoc(id, code, initialState);
    container.appendChild(iframe);
    this.debug?.logWidget(`canvas_iframe_mounted key=${widgetKey} id=${id}`);
    return iframe;
  }

  /**
   * Destroy an iframe inside a container to free memory.
   */
  destroyContainer(container: HTMLElement): void {
    const iframe = container.querySelector('iframe');
    if (iframe) {
      (iframe as HTMLIFrameElement).src = 'about:blank';
      iframe.remove();
    }
    container.innerHTML = '';
  }

  /** Reset state for new session */
  reset(): void {
    this.widgetObserver?.disconnect();
    this.initializedWidgets = new WeakMap();
    this.widgetObserver = null;
  }
}
