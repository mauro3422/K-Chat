import { describe, it, expect, beforeEach } from 'vitest';
import { WidgetContainerRenderer } from '../rendering/WidgetContainerRenderer';
import { WidgetRegistry } from '../core/widget/WidgetRegistry';
import { IframeBuilder } from '../rendering/IframeBuilder';
import { ContentHandler, StreamHandlerContext } from '../streaming/ContentHandler';
import { C } from '../core/infra/DomContracts';
import type { IStreamDispatcher } from '../types/dispatcher';
import type { IIframeBuilder } from '../types/iframe';

const noop = () => {};
const renderMarkdown = (text: string) => text;

function mockDispatcher(): IStreamDispatcher<StreamHandlerContext> {
  return { on: noop, off: noop, emit: noop, removeAll: noop };
}

function mockIframeBuilder(): IIframeBuilder {
  return {
    stateManager: undefined,
    buildSrcDoc: () => '',
    initAll: noop,
    handleMessage: noop,
    createCanvasIframe: () => document.createElement('iframe'),
    reset: noop,
  };
}

// ── Helpers ──

function makeContext(msgEl: HTMLElement, phaseIndex = 0): StreamHandlerContext {
  return {
    msgEl,
    bodyEl: null,
    reasoningTexts: [],
    contentTexts: [],
    phaseIndex,
    firstToken: true,
    _renderedKeys: {},
  };
}

// ═══════════════════════════════════════════════════════════════════
// Test 1: WidgetContainerRenderer.processWidgetContainers()
// ═══════════════════════════════════════════════════════════════════

describe('WidgetContainerRenderer.processWidgetContainers', () => {
  let renderer: WidgetContainerRenderer;

  beforeEach(() => {
    const registry = new WidgetRegistry();
    const iframeBuilder = new IframeBuilder(registry);
    renderer = new WidgetContainerRenderer(iframeBuilder);
  });

  it('detects ```html-widget block with key, code, correct index/end', () => {
    const text = '```html-widget demo\ncode\n```';
    const bodyDiv = document.createElement('div');
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});

    expect(result.widgetMatches).toHaveLength(1);
    const m = result.widgetMatches[0];
    expect(m.key).toBe('demo');
    expect(m.code).toBe('code');
    expect(m.codeBlock).toBe(true);
    expect(m.isNew).toBe(true);
    expect(m.index).toBe(0);
  });

  it('detects [Widget: key] tag', () => {
    const text = '[Widget: chart]';
    const bodyDiv = document.createElement('div');
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});

    expect(result.widgetMatches).toHaveLength(1);
    const m = result.widgetMatches[0];
    expect(m.key).toBe('chart');
    expect(m.code).toBeUndefined();
    expect(m.codeBlock).toBe(false);
    expect(m.isNew).toBe(true);
    expect(result.textToRender).toBe('[Widget: chart]');
  });

  it('returns empty widgetMatches for text without widgets', () => {
    const text = 'Just plain text with no widget markers.';
    const bodyDiv = document.createElement('div');
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});

    expect(result.widgetMatches).toHaveLength(0);
    expect(result.textToRender).toBe(text);
  });

  it('detects multiple widget tags in correct order', () => {
    const text = '[Widget: first] some [Widget: second]';
    const bodyDiv = document.createElement('div');
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});

    expect(result.widgetMatches).toHaveLength(2);
    expect(result.widgetMatches[0].key).toBe('first');
    expect(result.widgetMatches[1].key).toBe('second');
    expect(result.widgetMatches[0].index).toBeLessThan(result.widgetMatches[1].index);
  });

  it('ignores widget markers inside inline code backticks', () => {
    const text = 'some `[Widget: chart]` here';
    const bodyDiv = document.createElement('div');
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});

    expect(result.widgetMatches).toHaveLength(0);
  });

  it('ignores ```html-widget marker inside inline code', () => {
    const text = '` ```html-widget demo`\ncode\n```';
    const bodyDiv = document.createElement('div');
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});

    expect(result.widgetMatches).toHaveLength(0);
  });

  it('returns isNew=false on second call with same _renderedKeys', () => {
    const text = '[Widget: dup]';
    const bodyDiv = document.createElement('div');
    const renderedKeys: Record<string, boolean> = {};

    const first = renderer.processWidgetContainers(text, bodyDiv, {}, renderedKeys);
    expect(first.widgetMatches[0].isNew).toBe(true);

    const second = renderer.processWidgetContainers(text, bodyDiv, {}, renderedKeys);
    expect(second.widgetMatches[0].isNew).toBe(false);
  });
});

// ═══════════════════════════════════════════════════════════════════
// Test 2: WidgetRegistry.extract()
// ═══════════════════════════════════════════════════════════════════

describe('WidgetRegistry.extract', () => {
  let registry: WidgetRegistry;

  beforeEach(() => {
    registry = new WidgetRegistry();
  });

  it('replaces ```html-widget block with container div', () => {
    const text = '```html-widget demo\ncode\n```';
    const result = registry.extract(text);
    expect(result).toContain('class="interactive-widget-container"');
    expect(result).toContain('data-widget-id="widget-0"');
    expect(result).toContain('data-widget-key="demo"');
    expect(result).not.toContain('```html-widget');
  });

  it('replaces [Widget: key] tag with container div', () => {
    const text = '[Widget: chart]';
    const result = registry.extract(text);
    expect(result).toContain('class="interactive-widget-container"');
    expect(result).toContain('data-widget-id="widget-0"');
    expect(result).toContain('data-widget-key="chart"');
    expect(result).not.toContain('[Widget: chart]');
  });

  it('does NOT replace tilde-delimited html-widget blocks (not yet supported)', () => {
    const text = '~~~html-widget demo\ncode\n~~~';
    const result = registry.extract(text);
    expect(result).toBe(text);
  });

  it('does NOT replace [Widget: key] inside inline code backticks', () => {
    const text = 'text `[Widget: chart]` more';
    const result = registry.extract(text);
    expect(result).toContain('`[Widget: chart]`');
    expect(result).not.toContain('interactive-widget-container');
  });

  it('returns text unchanged when no widgets present', () => {
    const text = 'Just some plain markdown **content**.';
    const result = registry.extract(text);
    expect(result).toBe(text);
  });
});

// ═══════════════════════════════════════════════════════════════════
// Test 3: ContentHandler.ensureBody()
// ═══════════════════════════════════════════════════════════════════

describe('ContentHandler.ensureBody', () => {
  let contentHandler: ContentHandler;
  let msgEl: HTMLElement;

  beforeEach(() => {
    const widgetRegistry = new WidgetRegistry();
    const iframeBuilder = new IframeBuilder(widgetRegistry);
    const renderer = new WidgetContainerRenderer(iframeBuilder);
    contentHandler = new ContentHandler(
      mockDispatcher(),
      mockIframeBuilder(),
      renderer,
      widgetRegistry,
      renderMarkdown,
    );
    msgEl = document.createElement('div');
  });

  it('creates body div with correct className and data-phase', () => {
    const ctx = makeContext(msgEl, 1);
    const bodyEl = (contentHandler as any).ensureBody(ctx);

    expect(bodyEl.className).toBe(C.MSG_BODY);
    expect(bodyEl.getAttribute('data-phase')).toBe('1');
    expect(msgEl.contains(bodyEl)).toBe(true);
  });

  it('removes stale placeholder (body without data-phase)', () => {
    const stale = document.createElement('div');
    stale.className = C.MSG_BODY;
    stale.textContent = 'old placeholder';
    msgEl.appendChild(stale);

    const ctx = makeContext(msgEl, 0);
    (contentHandler as any).ensureBody(ctx);

    expect(msgEl.querySelector('.msg-body:not([data-phase])')).toBeNull();
    expect(msgEl.children.length).toBe(1);
  });

  it('returns existing body if already present for that phase', () => {
    const existing = document.createElement('div');
    existing.className = C.MSG_BODY;
    existing.setAttribute('data-phase', '0');
    msgEl.appendChild(existing);

    const ctx = makeContext(msgEl, 0);
    const bodyEl = (contentHandler as any).ensureBody(ctx);

    expect(bodyEl).toBe(existing);
    expect(msgEl.children.length).toBe(1);
  });
});

// ═══════════════════════════════════════════════════════════════════
// Test 4: ContentHandler.buildContainerLookup()
// ═══════════════════════════════════════════════════════════════════

describe('ContentHandler.buildContainerLookup', () => {
  let contentHandler: ContentHandler;

  beforeEach(() => {
    const widgetRegistry = new WidgetRegistry();
    const iframeBuilder = new IframeBuilder(widgetRegistry);
    const renderer = new WidgetContainerRenderer(iframeBuilder);
    contentHandler = new ContentHandler(
      mockDispatcher(),
      mockIframeBuilder(),
      renderer,
      widgetRegistry,
      renderMarkdown,
    );
  });

  it('returns containerByKey mapping from data-widget-key attributes', () => {
    const bodyDiv = document.createElement('div');

    const con1 = document.createElement('div');
    con1.className = C.WIDGET_CONTAINER;
    con1.setAttribute('data-widget-key', 'chart');
    bodyDiv.appendChild(con1);

    const con2 = document.createElement('div');
    con2.className = C.WIDGET_CONTAINER;
    con2.setAttribute('data-widget-key', 'focus-terminal');
    bodyDiv.appendChild(con2);

    const result = (contentHandler as any).buildContainerLookup(bodyDiv);
    expect(result['chart']).toBe(con1);
    expect(result['focus-terminal']).toBe(con2);
  });

  it('returns empty record when bodyDiv has no containers', () => {
    const bodyDiv = document.createElement('div');
    const result = (contentHandler as any).buildContainerLookup(bodyDiv);
    expect(result).toEqual({});
  });
});

// ═══════════════════════════════════════════════════════════════════
// Test 5: Widget pipeline end-to-end (simulated)
// ═══════════════════════════════════════════════════════════════════

describe('Widget pipeline end-to-end', () => {
  it('processes content with widget, creates containers, and mounts iframes', () => {
    // ── Real components ──
    const registry = new WidgetRegistry();
    const iframeBuilder = new IframeBuilder(registry);
    const renderer = new WidgetContainerRenderer(iframeBuilder);

    const msgEl = document.createElement('div');
    const bodyDiv = document.createElement('div');
    bodyDiv.className = C.MSG_BODY;
    bodyDiv.setAttribute('data-phase', '0');
    msgEl.appendChild(bodyDiv);

    // 1. processWidgetContainers
    const text = '```html-widget demo\n<button>Hello</button>\n```';
    const result = renderer.processWidgetContainers(text, bodyDiv, {}, {});
    expect(result.widgetMatches).toHaveLength(1);

    // 2. Simulate ensureWidgetContainers: register code and create container div
    const wm = result.widgetMatches[0];
    const id = registry.register(wm.code!, wm.key);
    const con = document.createElement('div');
    con.className = C.WIDGET_CONTAINER;
    con.setAttribute('data-widget-id', id);
    con.setAttribute('data-widget-key', wm.key || '');
    bodyDiv.appendChild(con);

    // Verify container in DOM
    const containers = bodyDiv.querySelectorAll('.' + C.WIDGET_CONTAINER);
    expect(containers).toHaveLength(1);
    const container = containers[0] as HTMLElement;
    expect(container.getAttribute('data-widget-key')).toBe('demo');
    expect(container.getAttribute('data-widget-id')).toBe('widget-0');

    // 3. IframeBuilder.initAll
    iframeBuilder.initAll(bodyDiv, true);

    // Verify iframe is created inside container
    const iframe = container.querySelector('iframe');
    expect(iframe).not.toBeNull();
    expect(iframe!.className).toBe(C.WIDGET_IFRAME);
    expect(iframe!.srcdoc).toContain('<button>Hello</button>');
  });
});
