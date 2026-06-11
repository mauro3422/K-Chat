import { describe, test, expect } from 'vitest';
import './setup.js';

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
  querySelector(sel) {
    if (sel.startsWith('[data-widget-key="')) {
      var key = sel.replace('[data-widget-key="', '').replace('"]', '');
      var traverse = function(node) {
        for (var c = 0; c < node.children.length; c++) {
          var child = node.children[c];
          if (child.getAttribute && child.getAttribute('data-widget-key') === key) return child;
          var found = traverse(child);
          if (found) return found;
        }
        return null;
      };
      return traverse(this);
    }
    if (sel === '.interactive-widget-container') {
      var traverse2 = function(node) {
        for (var c = 0; c < node.children.length; c++) {
          var child = node.children[c];
          if (child.className === 'interactive-widget-container') return child;
          var found = traverse2(child);
          if (found) return found;
        }
        return null;
      };
      return traverse2(this);
    }
    if (sel === '.msg-text-segment') {
      var traverse3 = function(node) {
        for (var c = 0; c < node.children.length; c++) {
          var child = node.children[c];
          if (child.className === 'msg-text-segment') return child;
          var found = traverse3(child);
          if (found) return found;
        }
        return null;
      };
      return traverse3(this);
    }
    return this;
  }
  insertAdjacentElement(pos, el) {
    if (pos === 'afterend') {
      var parent = this.parentNode || this;
      var idx = parent.children.indexOf(this);
      if (idx >= 0) {
        parent.children.splice(idx + 1, 0, el);
        el.parentNode = parent;
      } else {
        parent.children.push(el);
        el.parentNode = parent;
      }
    } else if (pos === 'beforebegin') {
      var parent2 = this.parentNode || this;
      var idx2 = parent2.children.indexOf(this);
      if (idx2 >= 0) {
        parent2.children.splice(idx2, 0, el);
        el.parentNode = parent2;
      } else {
        parent2.children.push(el);
        el.parentNode = parent2;
      }
    } else {
      this.children.push(el);
      el.parentNode = this;
    }
    return el;
  }
}

global.document = { createElement: (tag) => new MockElement(tag) };

function mockExtract(text) {
  var widgetRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)(?:\n```|$)/g;
  var result = text.replace(widgetRegex, function(match, key, code) {
    var id = 'widget-' + global.KairosWidgets.index++;
    code = code.replace(/\?\.([\w.]+)\s*=(?!=)/g, '.$1 =');
    global.KairosWidgets.registry[id] = code;
    if (key) {
      return '<div class="interactive-widget-container" data-widget-id="' + id + '" data-widget-key="' + key + '"></div>';
    }
    return '<div class="interactive-widget-container" data-widget-id="' + id + '"></div>';
  });

  var tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
  var seenKeys = {};
  result = result.replace(tagRegex, function(match, key) {
    var lowerKey = key.toLowerCase();
    if (seenKeys[lowerKey]) return '';
    seenKeys[lowerKey] = true;
    var id = 'widget-' + global.KairosWidgets.index++;
    return '<div class="interactive-widget-container" data-widget-id="' + id + '" data-widget-key="' + key + '"></div>';
  });

  return result;
}

global.KairosWidgets = {
  index: 0,
  nextIndex: function() { return this.index++; },
  registry: {},
  initAll: function() {},
  reset: function() { this.registry = {}; this.index = 0; },
  debug: {},
  extract: mockExtract
};
global.KairosMarkdown = { parse: function(t) { return '<p>' + t + '</p>'; } };
global.DOMPurify = { sanitize: function(t) { return t; } };
global.KairosUtils = { escHtml: function(s) { return String(s); } };
global.logUI = function() {};

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

  test('creates single msg-text-segment for text content', () => {
    const state = makeState();
    KairosStream.emit('content', 'Hola ', state);
    const bodyDiv = state.bodyDivs[0];
    expect(bodyDiv.children.length).toBe(1);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
  });

  test('calls KairosWidgets.extract() which populates registry', () => {
    KairosWidgets.reset();
    const state = makeState();
    KairosStream.emit('content', '```html-widget\n<div>Test</div>\n```', state);
    const keys = Object.keys(KairosWidgets.registry);
    expect(keys.length).toBeGreaterThan(0);
    expect(KairosWidgets.registry[keys[0]]).toContain('<div>Test</div>');
  });

  test('renders widget containers in innerHTML via extract()', () => {
    KairosWidgets.reset();
    const state = makeState();
    KairosStream.emit('content', 'Widget:\n```html-widget\n<div>W</div>\n```\nEnd.', state);
    const bodyDiv = state.bodyDivs[0];
    expect(bodyDiv.children.length).toBe(1);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
    expect(bodyDiv.children[0].innerHTML).toContain('interactive-widget-container');
    expect(bodyDiv.children[0].innerHTML).toContain('data-widget-id');
  });

  test('cache key prevents redundant re-rendering', () => {
    const state = makeState({ contentTexts: ['Hello'] });
    KairosStream.emit('content', '', state);
    const prevRawText = state.bodyDivs[0].children[0]?.dataset?.rawText;
    KairosStream.emit('content', '', state);
    expect(state.bodyDivs[0].children[0]?.dataset?.rawText).toBe(prevRawText);
  });

  test('calls initAll() after rendering widget containers', () => {
    var initAllCalled = false;
    var origInitAll = global.KairosWidgets.initAll;
    global.KairosWidgets.initAll = function() { initAllCalled = true; };

    const state = makeState();
    KairosStream.emit('content', '[Widget: foo]', state);

    global.KairosWidgets.initAll = origInitAll;
    expect(initAllCalled).toBe(true);
  });
});

describe('anti-regression', () => {

  test('widget dedup - extract() handles duplicate [Widget: x] tags', () => {
    KairosWidgets.reset();
    const state = makeState();
    KairosStream.emit('content', '[Widget: alpha] stuff [Widget: alpha] more [Widget: alpha]', state);
    const bodyDiv = state.bodyDivs[0];
    expect(bodyDiv.children.length).toBe(1);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
    expect(bodyDiv.children[0].innerHTML).toContain('interactive-widget-container');
    var containerCount = (bodyDiv.children[0].innerHTML.match(/interactive-widget-container/g) || []).length;
    expect(containerCount).toBe(1);
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

  test('shouldRetry allows retry with successful tools', async () => {
    const { RetryHandler } = await import('../web/static/modules/retry-handler.js');
    RetryHandler.resetRetryCount();
    const result = RetryHandler.shouldRetry(false);
    expect(result).toBe(true);
    expect(RetryHandler.getRetryCount()).toBe(0);
  });
});
