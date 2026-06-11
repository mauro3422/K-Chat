import { describe, test, expect } from 'vitest';
import './setup.js';

// Stream-renderer specific mocks
class MockElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.className = '';
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.innerHTML = '';
    this._textContent = '';
    this.open = true;
  }
  get textContent() { return this._textContent; }
  set textContent(val) {
    this._textContent = val;
    if (val === '') this.children = [];
  }
  get lastChild() { return this.children[this.children.length - 1]; }
  get classList() {
    const self = this;
    return { contains: (cls) => self.className.split(/\s+/).indexOf(cls) >= 0 };
  }
  appendChild(el) { el.parentNode = this; this.children.push(el); return el; }
  removeChild(el) {
    const idx = this.children.indexOf(el);
    if (idx >= 0) { this.children.splice(idx, 1); el.parentNode = null; }
    return el;
  }
  insertBefore(newEl, refEl) {
    const idx = this.children.indexOf(refEl);
    if (idx >= 0) { this.children.splice(idx, 0, newEl); newEl.parentNode = this; }
    else { this.appendChild(newEl); }
    return newEl;
  }
  setAttribute(name, val) { this.attributes[name] = val; }
  getAttribute(name) { return this.attributes[name]; }
  querySelectorAll(sel) {
    const res = [];
    const traverse = (node) => {
      for (const child of node.children) {
        if (sel === '.interactive-widget-container' && child.className === 'interactive-widget-container') res.push(child);
        else if (sel === '.msg-text-segment' && child.className === 'msg-text-segment') res.push(child);
        traverse(child);
      }
    };
    traverse(this);
    return res;
  }
  querySelector(sel) { return this; }
  insertAdjacentElement(pos, el) { this.children.push(el); return el; }
}

global.document = { createElement: (tag) => new MockElement(tag) };

const listeners = {};
global.KairosStream = {
  on: (evt, cb) => { listeners[evt] = cb; },
  emit: (evt, ...args) => { if (listeners[evt]) listeners[evt](...args); }
};

const mockReasoningState = { enter: () => false, exit: () => {} };

await import('../web/static/modules/content-handler.js');

function makeState(overrides) {
  return Object.assign({
    asstDiv: new MockElement('div'),
    bodyDivs: [new MockElement('div')],
    reasoningEls: [],
    contentTexts: [''],
    reasoningText: '',
    reasoningState: mockReasoningState
  }, overrides || {});
}

describe('content-handler', () => {

  test('safely initializes widgetMap', () => {
    KairosWidgets.reset();
    const state = makeState();
    KairosStream.emit('content', 'Hola ', state);
    expect(state.widgetMap).toBeDefined();
    expect(state.widgetMap[0]).toBeDefined();
  });

  test('creates text segment and widget container for widget block', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = makeState();
    KairosStream.emit('content', 'Widget:\n```html-widget\n<div>W</div>\n```\nEnd.', state);
    const bodyDiv = state.bodyDivs[0];
    expect(bodyDiv.children.length).toBe(3);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
    expect(bodyDiv.children[1].className).toBe('interactive-widget-container');
    expect(bodyDiv.children[2].className).toBe('msg-text-segment');
  });

  test('registers widget in KairosWidgets.registry', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = makeState();
    KairosStream.emit('content', '```html-widget\n<div>Test</div>\n```', state);
    const keys = Object.keys(KairosWidgets.registry);
    expect(keys.length).toBeGreaterThan(0);
    expect(KairosWidgets.registry[keys[0]]).toContain('<div>Test</div>');
  });

  test('sets data-widget-id on container', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = makeState();
    KairosStream.emit('content', '```html-widget\n<div>X</div>\n```', state);
    const container = state.bodyDivs[0].children[1];
    expect(container.getAttribute('data-widget-id')).toBeDefined();
  });

  test('cache key prevents redundant re-rendering', () => {
    const state = makeState({ contentTexts: ['Hello'] });
    KairosStream.emit('content', '', state);
    const prevRawText = state.bodyDivs[0].children[0]?.dataset?.rawText;
    KairosStream.emit('content', '', state);
    expect(state.bodyDivs[0].children[0]?.dataset?.rawText).toBe(prevRawText);
  });
});

describe('anti-regression', () => {

  test('widget dedup - multiple same-key [Widget: x] tags produce ONE container', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = makeState();
    KairosStream.emit('content', '[Widget: alpha] stuff [Widget: alpha] more [Widget: alpha]', state);
    const bodyDiv = state.bodyDivs[0];
    expect(bodyDiv.children.length).toBe(3);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
    expect(bodyDiv.children[1].className).toBe('interactive-widget-container');
    expect(bodyDiv.children[2].className).toBe('msg-text-segment');
    const containers = bodyDiv.querySelectorAll('.interactive-widget-container');
    expect(containers.length).toBe(1);
  });

  test('widget cache is phase-scoped (no cross-phase contamination)', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = makeState({
      reasoningEls: [new MockElement('details'), new MockElement('details')],
      _widgetCache: {
        0: { matches: [{ index: 0, end: 10, key: 'alpha', code: '', full: '[Widget: alpha]', fromTag: true }], prevLen: 100 }
      }
    });
    KairosStream.emit('content', '[Widget: beta]', state);
    expect(state._widgetCache[0].matches[0].key).toBe('alpha');
    expect(state._widgetCache[1].matches[0].key).toBe('beta');
  });

  test('multi-turn with no tools still creates new details', async () => {
    const { ReasoningState } = await import('../web/static/modules/reasoning-state.js');
    await import('../web/static/modules/reasoning-handler.js');

    const rs = new ReasoningState();
    const state = makeState({ reasoningState: rs });

    KairosStream.emit('reasoning', 'Step 1...', state);
    expect(state.reasoningEls.length).toBe(1);

    KairosStream.emit('content', 'Response', state);
    expect(rs.isActive).toBe(false);

    KairosStream.emit('reasoning', 'Step 2...', state);
    expect(state.reasoningEls.length).toBe(2);
  });

  test('cache prevLen always updates (staleness fix)', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = makeState();

    KairosStream.emit('content', '[Widget: x]', state);
    expect(state._widgetCache[0].prevLen).toBe('[Widget: x]'.length);

    KairosStream.emit('content', ' hello', state);
    expect(state._widgetCache[0].prevLen).toBe(state.contentTexts[0].length);
  });

  test('shouldRetry allows retry with successful tools', async () => {
    const { RetryHandler } = await import('../web/static/modules/retry-handler.js');
    RetryHandler.resetRetryCount();
    const result = RetryHandler.shouldRetry(false);
    expect(result).toBe(true);
    expect(RetryHandler.getRetryCount()).toBe(0);
  });
});
