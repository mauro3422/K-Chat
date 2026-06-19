import { IStreamDispatcher } from '../types/dispatcher';
import { IWidgetRegistry } from '../types/widgets';
import { IIframeBuilder } from '../types/iframe';
import { IWidgetContainerRenderer } from '../types/widget-renderer';
import { IDebugManager } from '../types/debug';
import { getLogger } from '../core/LoggerFactory';
import { ILogger } from '../core/Logger';
import { C } from '../core/DomContracts';
import { ReasoningHandler } from './reasoning-handler';
import { ToolCallRenderer } from './tool-call-renderer';
import { ErrorRenderer } from './error-renderer';

export interface StreamHandlerContext {
  msgEl: HTMLElement;
  bodyEl: HTMLElement | null;
  reasoningTexts: string[];
  contentTexts: string[];
  phaseIndex: number;
  firstToken: boolean;
  _renderedKeys: Record<string, boolean>;
}

/**
 * ContentHandler — orchestrates the streaming content pipeline.
 *
 * CRITICAL: NEVER removes widget containers from the DOM (preserves iframes).
 * Only text segments are removed/recreated.
 * Containers stay at their DOM positions; text segments are inserted between them.
 *
 * NOW RECEIVES IWidgetRegistry via constructor (no static imports).
 */
export class ContentHandler {
  private dispatcher: IStreamDispatcher<StreamHandlerContext>;
  private iframeBuilder: IIframeBuilder;
  private containerRenderer: IWidgetContainerRenderer;
  private registry: IWidgetRegistry;
  private renderMarkdown: (markdown: string) => string;
  private debug?: IDebugManager;
  private logger: ILogger;
  private reasoningHandler: ReasoningHandler;
  private toolCallRenderer: ToolCallRenderer;
  private errorRenderer: ErrorRenderer;
  private lastRenderedLength = 0;

  constructor(
    dispatcher: IStreamDispatcher<StreamHandlerContext>,
    iframeBuilder: IIframeBuilder,
    containerRenderer: IWidgetContainerRenderer,
    registry: IWidgetRegistry,
    renderMarkdown: (markdown: string) => string,
    debug?: IDebugManager,
  ) {
    this.dispatcher = dispatcher;
    this.iframeBuilder = iframeBuilder;
    this.containerRenderer = containerRenderer;
    this.registry = registry;
    this.renderMarkdown = renderMarkdown;
    this.debug = debug;
    this.logger = getLogger('stream');
    this.reasoningHandler = new ReasoningHandler(
      (ctx, el) => this.insertBeforeBody(ctx, el),
      (msgEl) => this.autoScroll(msgEl),
      debug,
    );
    this.toolCallRenderer = new ToolCallRenderer(
      (ctx, el) => this.insertBeforeBody(ctx, el),
      (msgEl) => this.autoScroll(msgEl),
      debug,
    );
    this.errorRenderer = new ErrorRenderer(
      (ctx) => this.ensureBody(ctx),
      (str) => ContentHandler.escHtml(str),
      debug,
    );
    this.registerHandlers();
  }

  private registerHandlers(): void {
    this.dispatcher.on('reasoning', (data, ctx: StreamHandlerContext) => this.reasoningHandler.handleReasoning(data, ctx));
    this.dispatcher.on('content', (data, ctx: StreamHandlerContext) => this.handleContent(data, ctx));
    this.dispatcher.on('tool_call', (data, ctx: StreamHandlerContext) => this.toolCallRenderer.handleToolCall(data, ctx));
    this.dispatcher.on('memory', (data, ctx: StreamHandlerContext) => this.reasoningHandler.handleMemory(data, ctx));
    this.dispatcher.on('error', (data, ctx: StreamHandlerContext) => this.errorRenderer.handleError(data, ctx));
  }

  createContext(msgEl: HTMLElement): StreamHandlerContext {
    return {
      msgEl, bodyEl: null, reasoningTexts: [], contentTexts: [],
      phaseIndex: 0, firstToken: true, _renderedKeys: {},
    };
  }

  /** Get or create a phase-specific body div — each content phase has its own body.
   *  This matches the old JS behavior where each phase had a separate body div,
   *  preventing widget iframe destruction on phase transitions. */
  private ensureBody(ctx: StreamHandlerContext): HTMLElement {
    const phaseIdx = ctx.phaseIndex;
    // Remove stale placeholder body (created by beginStreaming, has no data-phase)
    const staleBody = ctx.msgEl.querySelector('.' + C.MSG_BODY + ':not([data-phase])') as HTMLElement | null;
    if (staleBody) staleBody.remove();
    const selector = '.' + C.MSG_BODY + '[data-phase="' + phaseIdx + '"]';
    let bodyEl = ctx.msgEl.querySelector(selector) as HTMLElement | null;
    if (!bodyEl) {
      bodyEl = document.createElement('div');
      bodyEl.className = C.MSG_BODY;
      bodyEl.setAttribute('data-phase', String(phaseIdx));
      ctx.msgEl.appendChild(bodyEl);
    }
    ctx.bodyEl = bodyEl;
    return bodyEl;
  }

  private insertBeforeBody(ctx: StreamHandlerContext, el: HTMLElement): void {
    const phase = parseInt(el.getAttribute('data-phase') || String(ctx.phaseIndex), 10);
    for (let p = phase; p <= ctx.phaseIndex + 1; p++) {
      const body = ctx.msgEl.querySelector(`.${C.MSG_BODY}[data-phase="${p}"]`);
      if (body) {
        ctx.msgEl.insertBefore(el, body);
        return;
      }
    }
    ctx.msgEl.appendChild(el);
  }

  private static setSegmentContent(targetSeg: HTMLElement, html: string, incompleteTail?: string): void {
    let renderedHtml = html || '';
    if (incompleteTail) renderedHtml += '<pre style="opacity:0.6"><code>' + this.escHtml(incompleteTail) + '</code></pre>';
    if (typeof targetSeg.replaceChildren === 'function') { targetSeg.replaceChildren(); }
    else { while (targetSeg.firstChild) targetSeg.removeChild(targetSeg.firstChild); }

    if (!renderedHtml) return;
    targetSeg.insertAdjacentHTML('beforeend', renderedHtml);
  }

  private static escHtml(str: string): string {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  // ── Content handling ────────────────────────────────

  /** Remove all text segments from body (containers are never removed) */
  private removeTextSegments(bodyDiv: HTMLElement): void {
    const oldSegs = bodyDiv.querySelectorAll('.' + C.MSG_TEXT_SEGMENT);
    for (let i = oldSegs.length - 1; i >= 0; i--) {
      const seg = oldSegs[i];
      if (seg.parentNode) seg.parentNode.removeChild(seg);
    }
  }

  /** Build a lookup of current containers by key */
  private buildContainerLookup(bodyDiv: HTMLElement): Record<string, HTMLElement> {
    const currentContainers = bodyDiv.querySelectorAll('.' + C.WIDGET_CONTAINER);
    const containerByKey: Record<string, HTMLElement> = {};
    for (let ci = 0; ci < currentContainers.length; ci++) {
      const con = currentContainers[ci] as HTMLElement;
      const key = con.getAttribute('data-widget-key');
      if (key) containerByKey[key] = con;
    }
    return containerByKey;
  }

  /** Ensure DOM has the correct number of widget containers, adding missing ones */
  private ensureWidgetContainers(
    bodyDiv: HTMLElement,
    widgetMatches: Array<{ index: number; end: number; key?: string; code?: string; isNew: boolean; codeBlock: boolean }>,
    containerByKey: Record<string, HTMLElement>,
  ): void {
    for (let i = 0; i < widgetMatches.length; i++) {
      const wm = widgetMatches[i];
      const lookupKey = wm.key || (wm.codeBlock ? '_pos_' + (wm.index || 0) : undefined);

      if (lookupKey && containerByKey[lookupKey]) continue;
      if (wm.codeBlock && !wm.isNew) continue;

      if (wm.isNew && wm.code) {
        const id = this.registry.register(wm.code, wm.key);
        const con = document.createElement('div');
        con.className = C.WIDGET_CONTAINER;
        con.setAttribute('data-widget-id', id);
        if (lookupKey) con.setAttribute('data-widget-key', lookupKey);
        bodyDiv.appendChild(con);
        containerByKey[lookupKey || ''] = con;
        this.debug?.logWidget(`new_container wid=${id} key=${lookupKey} codeLen=${wm.code.length}`);
      } else if (wm.isNew && !wm.code) {
        const id = this.registry.nextIndex();
        const con = document.createElement('div');
        con.className = C.WIDGET_CONTAINER;
        con.setAttribute('data-widget-id', id);
        if (lookupKey) con.setAttribute('data-widget-key', lookupKey);
        bodyDiv.appendChild(con);
        containerByKey[lookupKey || ''] = con;
        this.debug?.logWidget(`new_container_tag wid=${id} key=${lookupKey}`);
      }
    }
  }

  /** Remove excess containers if widget count decreased */
  private removeExcessContainers(bodyDiv: HTMLElement, expectedCount: number): void {
    const containers = Array.from(bodyDiv.querySelectorAll('.' + C.WIDGET_CONTAINER));
    while (containers.length > expectedCount) {
      const last = containers.pop()!;
      if (last.parentNode) last.parentNode.removeChild(last);
    }
  }

  /** Insert text segment divs at even positions (0, 2, 4...) pushing containers to odd positions */
  private insertTextSegments(bodyDiv: HTMLElement): void {
    const finalContainers = bodyDiv.querySelectorAll('.' + C.WIDGET_CONTAINER);

    const seg0 = document.createElement('div');
    seg0.className = C.MSG_TEXT_SEGMENT;
    if (finalContainers.length > 0) {
      bodyDiv.insertBefore(seg0, finalContainers[0]);
    } else {
      bodyDiv.appendChild(seg0);
    }

    for (let i = 0; i < finalContainers.length; i++) {
      const con = finalContainers[i];
      const nextSibling = con.nextSibling;
      const seg = document.createElement('div');
      seg.className = C.MSG_TEXT_SEGMENT;
      if (nextSibling) {
        bodyDiv.insertBefore(seg, nextSibling);
      } else {
        bodyDiv.appendChild(seg);
      }
    }
  }

  /** Render markdown into text segments, using cache to avoid unnecessary DOM updates */
  private renderTextSegments(
    bodyDiv: HTMLElement,
    textToRender: string,
    widgetMatches: Array<{ index: number; end: number; key?: string; code?: string; isNew: boolean; codeBlock: boolean }>,
    incompleteTail: string,
  ): void {
    const textSegments = bodyDiv.querySelectorAll('.' + C.MSG_TEXT_SEGMENT);
    for (let i = 0; i < textSegments.length; i++) {
      const start = i === 0 ? 0 : widgetMatches[i - 1].end;
      const end = i === widgetMatches.length ? textToRender.length : widgetMatches[i].index;
      const segText = textToRender.substring(start, end);

      const targetSeg = textSegments[i] as HTMLElement;
      if (!targetSeg) continue;
      if (!segText && !(i === widgetMatches.length && incompleteTail)) {
        targetSeg.innerHTML = '';
        continue;
      }

      const cacheKey = segText + '|' + incompleteTail + '|' + (i === widgetMatches.length ? '' : (widgetMatches[i]?.key || ''));
      if (targetSeg.dataset.rawText === cacheKey) continue;
      targetSeg.dataset.rawText = cacheKey;

      const html = this.renderMarkdown(segText);
      ContentHandler.setSegmentContent(targetSeg, html, i === widgetMatches.length ? incompleteTail : '');
    }
  }

  private handleContent(data: string, ctx: StreamHandlerContext): void {
    this.debug?.logStream('content', data);
    if (ctx.firstToken) ctx.firstToken = false;

    const bodyEl = this.ensureBody(ctx);
    bodyEl.classList.add('msg-body', 'md-content');

    if (!ctx.contentTexts[ctx.phaseIndex]) {
      ctx.contentTexts[ctx.phaseIndex] = '';
      this.lastRenderedLength = 0;
    }
    ctx.contentTexts[ctx.phaseIndex] += data;
    const fullText = ctx.contentTexts[ctx.phaseIndex];
    const bodyDiv = bodyEl;

    // ── Calculate expected structure ──
    const result = this.containerRenderer.processWidgetContainers(fullText, bodyDiv, {}, ctx._renderedKeys);
    const { textToRender, incompleteTail, widgetMatches } = result;

    // ── Incremental path: only update last text segment if no new widget boundaries ──
    const delta = fullText.slice(this.lastRenderedLength);
    const hasNewWidgetBoundary = delta ? /```html-widget|~~~widget-(?:start|end)|\[Widget\s*:\s*[\w\-]+\]/.test(delta) : false;

    if (this.lastRenderedLength > 0 && !hasNewWidgetBoundary && widgetMatches.length === 0) {
      const textSegments = bodyDiv.querySelectorAll(':scope > .' + C.MSG_TEXT_SEGMENT);
      if (textSegments.length > 0) {
        const lastSeg = textSegments[textSegments.length - 1] as HTMLElement;
        const lastSegIdx = textSegments.length - 1;
        const start = lastSegIdx === 0 ? 0 : widgetMatches[lastSegIdx - 1].end;
        const end = lastSegIdx === widgetMatches.length ? textToRender.length : widgetMatches[lastSegIdx].index;
        const segText = textToRender.substring(start, end);
        const html = this.renderMarkdown(segText);
        ContentHandler.setSegmentContent(lastSeg, html, lastSegIdx === widgetMatches.length ? incompleteTail : '');
      } else {
        const seg = document.createElement('div');
        seg.className = C.MSG_TEXT_SEGMENT;
        bodyDiv.appendChild(seg);
        const html = this.renderMarkdown(textToRender);
        ContentHandler.setSegmentContent(seg, html, incompleteTail);
      }
      this.lastRenderedLength = fullText.length;
      this.autoScroll(ctx.msgEl);
      return;
    }

    // ── Full regeneration ──
    this.removeTextSegments(bodyDiv);

    const containerByKey = this.buildContainerLookup(bodyDiv);
    this.ensureWidgetContainers(bodyDiv, widgetMatches, containerByKey);
    this.removeExcessContainers(bodyDiv, widgetMatches.length);

    this.insertTextSegments(bodyDiv);

    this.renderTextSegments(bodyDiv, textToRender, widgetMatches, incompleteTail);

    this.iframeBuilder.initAll(bodyDiv);

    this.lastRenderedLength = fullText.length;
    this.autoScroll(ctx.msgEl);
  }

  private _scrollRafId = 0;
  /** First event of a new stream gets an unconditional scroll */
  private _firstScroll = true;

  /** Scroll messages container to bottom when new content arrives.
   *  First event of a new stream always scrolls (to show the response starting).
   *  After that, only scrolls if user is near the bottom (within 300px).
   *  Throttled via requestAnimationFrame. */
  private autoScroll(msgEl: HTMLElement): void {
    if (this._scrollRafId) return;
    this._scrollRafId = requestAnimationFrame(() => {
      this._scrollRafId = 0;
      const container = document.getElementById('messages') as HTMLElement | null;
      if (!container) return;

      if (this._firstScroll) {
        this._firstScroll = false;
        container.scrollTop = container.scrollHeight;
        return;
      }

      const distFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distFromBottom > 300) return;

      container.scrollTop = container.scrollHeight;
    });
  }

}
