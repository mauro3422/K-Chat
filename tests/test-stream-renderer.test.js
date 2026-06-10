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
}

global.document = { createElement: (tag) => new MockElement(tag) };

const listeners = {};
global.KairosStream = {
  on: (evt, cb) => { listeners[evt] = cb; },
  emit: (evt, ...args) => { if (listeners[evt]) listeners[evt](...args); }
};

await import('../web/static/modules/content-handler.js');

describe('content-handler', () => {
  test('safely initializes widgetMap', () => {
    KairosWidgets.reset();
    const state = {
      asstDiv: new MockElement('div'),
      bodyDivs: [new MockElement('div')],
      reasoningEls: [],
      contentTexts: [''],
      reasoningText: '',
    };
    KairosStream.emit('content', 'Hola ', state);
    expect(state.widgetMap).toBeDefined();
    expect(state.widgetMap[0]).toBeDefined();
  });

  test('creates text segment and widget container for widget block', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = {
      asstDiv: new MockElement('div'),
      bodyDivs: [new MockElement('div')],
      reasoningEls: [],
      contentTexts: [''],
      reasoningText: '',
    };
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
    const state = {
      asstDiv: new MockElement('div'),
      bodyDivs: [new MockElement('div')],
      reasoningEls: [],
      contentTexts: [''],
      reasoningText: '',
    };
    KairosStream.emit('content', '```html-widget\n<div>Test</div>\n```', state);
    const keys = Object.keys(KairosWidgets.registry);
    expect(keys.length).toBeGreaterThan(0);
    expect(KairosWidgets.registry[keys[0]]).toContain('<div>Test</div>');
  });

  test('sets data-widget-id on container', () => {
    KairosWidgets.reset();
    global.KairosWidgets.index = 0;
    const state = {
      asstDiv: new MockElement('div'),
      bodyDivs: [new MockElement('div')],
      reasoningEls: [],
      contentTexts: [''],
      reasoningText: '',
    };
    KairosStream.emit('content', '```html-widget\n<div>X</div>\n```', state);
    const container = state.bodyDivs[0].children[1];
    expect(container.getAttribute('data-widget-id')).toBeDefined();
  });

  test('cache key prevents redundant re-rendering', () => {
    const state = {
      asstDiv: new MockElement('div'),
      bodyDivs: [new MockElement('div')],
      reasoningEls: [],
      contentTexts: ['Hello'],
      reasoningText: '',
    };
    KairosStream.emit('content', '', state);
    const prevRawText = state.bodyDivs[0].children[0]?.dataset?.rawText;
    KairosStream.emit('content', '', state);
    expect(state.bodyDivs[0].children[0]?.dataset?.rawText).toBe(prevRawText);
  });
});
