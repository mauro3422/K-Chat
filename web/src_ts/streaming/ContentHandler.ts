import { IStreamDispatcher } from '../types/dispatcher';
import { IWidgetRegistry } from '../types/widgets';
import { IIframeBuilder } from '../types/iframe';
import { IWidgetContainerRenderer } from '../types/widget-renderer';
import { renderMarkdown } from '../rendering/DomRenderer';
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
  private debug?: IDebugManager;
  private logger: ILogger;
  private reasoningHandler: ReasoningHandler;
  private toolCallRenderer: ToolCallRenderer;
  private errorRenderer: ErrorRenderer;

  constructor(
    dispatcher: IStreamDispatcher<StreamHandlerContext>,
    iframeBuilder: IIframeBuilder,
    containerRenderer: IWidgetContainerRenderer,
    registry: IWidgetRegistry,
    debug?: IDebugManager,
  ) {
    this.dispatcher = dispatcher;
    this.iframeBuilder = iframeBuilder;
    this.containerRenderer = containerRenderer;
    this.registry = registry;
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

  private ensureBody(ctx: StreamHandlerContext): HTMLElement {
    if (!ctx.bodyEl) {
      const existing = ctx.msgEl.querySelector('.' + C.MSG_BODY) as HTMLElement | null;
      if (existing) ctx.bodyEl = existing;
      else {
        ctx.bodyEl = document.createElement('div');
        ctx.bodyEl.className = C.MSG_BODY;
        ctx.msgEl.appendChild(ctx.bodyEl);
      }
    }
    return ctx.bodyEl;
  }

  private insertBeforeBody(ctx: StreamHandlerContext, el: HTMLElement): void {
    const body = ctx.bodyEl || ctx.msgEl.querySelector('.' + C.MSG_BODY);
    if (body) ctx.msgEl.insertBefore(el, body);
    else ctx.msgEl.appendChild(el);
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

  /** Build a lookup of current containers by key and by id */
  private buildContainerLookup(bodyDiv: HTMLElement): {
    containerByKey: Record<string, HTMLElement>;
    containerById: Record<string, HTMLElement>;
  } {
    const currentContainers = bodyDiv.querySelectorAll('.' + C.WIDGET_CONTAINER);
    const containerByKey: Record<string, HTMLElement> = {};
    const containerById: Record<string, HTMLElement> = {};
    for (let ci = 0; ci < currentContainers.length; ci++) {
      const con = currentContainers[ci] as HTMLElement;
      const key = con.getAttribute('data-widget-key');
      if (key) containerByKey[key] = con;
      const id = con.getAttribute('data-widget-id');
      if (id && !con.getAttribute('data-widget-key')) containerById[id] = con;
    }
    return { containerByKey, containerById };
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
    const allContainers = bodyDiv.querySelectorAll('.' + C.WIDGET_CONTAINER);
    while (allContainers.length > expectedCount) {
      const last = allContainers[allContainers.length - 1];
      if (last && last.parentNode) last.parentNode.removeChild(last);
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

      const html = renderMarkdown(segText);
      ContentHandler.setSegmentContent(targetSeg, html, i === widgetMatches.length ? incompleteTail : '');
    }
  }

  private handleContent(data: string, ctx: StreamHandlerContext): void {
    this.debug?.logStream('content', data);
    if (ctx.firstToken) ctx.firstToken = false;

    const bodyEl = this.ensureBody(ctx);
    bodyEl.classList.add('msg-body', 'md-content');

    if (!ctx.contentTexts[ctx.phaseIndex]) {
      bodyEl.innerHTML = '';
    }

    if (!ctx.contentTexts[ctx.phaseIndex]) ctx.contentTexts[ctx.phaseIndex] = '';
    ctx.contentTexts[ctx.phaseIndex] += data;
    const fullText = ctx.contentTexts[ctx.phaseIndex];
    const bodyDiv = bodyEl;

    // ── Calculate expected structure ──
    const result = this.containerRenderer.processWidgetContainers(fullText, bodyDiv, {}, ctx._renderedKeys);
    const { textToRender, incompleteTail, widgetMatches } = result;

    // ── Step 1: Remove text segments (safe — no iframes) ──
    this.removeTextSegments(bodyDiv);

    // ── Step 2-4: Build container lookup and add missing ones ──
    const { containerByKey, containerById } = this.buildContainerLookup(bodyDiv);
    this.ensureWidgetContainers(bodyDiv, widgetMatches, containerByKey);
    this.removeExcessContainers(bodyDiv, widgetMatches.length);

    // ── Step 5-6: Reorder containers and text segments ──
    this.insertTextSegments(bodyDiv);

    // ── Step 7: Render markdown in text segments ──
    this.renderTextSegments(bodyDiv, textToRender, widgetMatches, incompleteTail);

    // ── Step 8: Initialize any new widgets ──
    this.iframeBuilder.initAll(bodyDiv);

    // ── Step 9: Auto-scroll ──
    this.autoScroll(ctx.msgEl);
  }

  /** Scroll messages container to bottom unless user manually scrolled up */
  private autoScroll(msgEl: HTMLElement): void {
    requestAnimationFrame(() => {
      const container = document.getElementById('messages') as HTMLElement | null;
      if (!container) return;

      const distFromBottom = container.scrollHeight - container.scrollTop - container.clientHeight;
      if (distFromBottom > 100) return;

      container.scrollTop = container.scrollHeight;
    });
  }

}
