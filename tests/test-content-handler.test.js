import { describe, test, expect, beforeAll, beforeEach } from 'vitest';
import './setup.js';

function makeEl(tag) {
  var el = {
    tagName: (tag || 'DIV').toUpperCase(),
    className: '',
    dataset: {},
    children: [],
    innerHTML: '',
    _textContent: '',
    style: {},
    attributes: {},
    parentNode: null,
    get textContent() { return this._textContent; },
    set textContent(v) { this._textContent = String(v); },
    appendChild(child) {
      this.children.push(child);
      child.parentNode = this;
      return child;
    },
    removeChild(child) {
      var idx = this.children.indexOf(child);
      if (idx >= 0) this.children.splice(idx, 1);
    },
    get lastChild() { return this.children[this.children.length - 1] || null; },
    querySelector(sel) {
      if (sel && sel.startsWith('[data-widget-key="')) {
        var m = sel.match(/"(.*?)"/);
        if (m) {
          var key = m[1];
          return findDeep(this, function(n) {
            return n.attributes && n.attributes['data-widget-key'] === key;
          });
        }
      }
      return null;
    },
    querySelectorAll(sel) {
      var results = [];
      if (sel === '.interactive-widget-container') {
        walkDeep(this, function(n) {
          if (n.className && n.className.split(' ').indexOf('interactive-widget-container') >= 0) {
            results.push(n);
          }
        });
      }
      return results;
    },
    setAttribute(name, val) {
      this.attributes[name] = val;
      if (name.startsWith('data-')) this.dataset[name.slice(5)] = val;
    },
    getAttribute(name) { return this.attributes[name] || null; },
    closest() { return null; },
    classList: {
      _classes: [],
      add: function(c) { if (this._classes.indexOf(c) < 0) this._classes.push(c); },
      remove: function(c) { var i = this._classes.indexOf(c); if (i >= 0) this._classes.splice(i, 1); },
      toggle: function(c, force) {
        var has = this._classes.indexOf(c) >= 0;
        if (force === undefined) force = !has;
        if (force && !has) this._classes.push(c);
        else if (!force && has) this._classes.splice(this._classes.indexOf(c), 1);
        return force;
      },
      contains: function(c) { return this._classes.indexOf(c) >= 0; }
    },
    remove: function() {}
  };
  return el;
}

function findDeep(node, pred) {
  if (pred(node)) return node;
  for (var i = 0; i < node.children.length; i++) {
    var found = findDeep(node.children[i], pred);
    if (found) return found;
  }
  return null;
}

function walkDeep(node, fn) {
  fn(node);
  for (var i = 0; i < node.children.length; i++) {
    walkDeep(node.children[i], fn);
  }
}

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

global.document = {
  getElementById: function() { return null; },
  querySelector: function() { return null; },
  querySelectorAll: function() { return []; },
  createElement: function(tag) { return makeEl(tag); },
  addEventListener: function() {},
  body: { appendChild: function() {} },
  _listeners: {}
};

global.KairosWidgets = {
  index: 0,
  nextIndex: function() { return this.index++; },
  registry: {},
  initAll: function() {},
  reset: function() { this.registry = {}; this.index = 0; },
  debug: {},
  extract: mockExtract
};
global.DOMPurify = { sanitize: function(t) { return t; } };
global.KairosMarkdown = { parse: function(t) { return '<p>' + t + '</p>'; } };
global.KairosUtils = { escHtml: function(s) { return String(s); } };
global.logUI = function() {};

var handlingStream = {
  _cb: null,
  on: function(evt, cb) { if (evt === 'content') this._cb = cb; },
  emit: function() {}
};
var origStream = global.KairosStream;

beforeAll(async function() {
  global.KairosStream = handlingStream;
  await import('../web/static/modules/content-handler.js');
  global.KairosStream = origStream;
});

beforeEach(function() {
  global.KairosWidgets.index = 0;
  global.KairosWidgets.registry = {};
});

describe('Content Handler', function() {
  test('creates single widget container via extract() for duplicate marker', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('[Widget: foo] y otro [Widget: foo] en el mismo texto', state);

    var html = bodyDiv.children[0].innerHTML;
    var containerCount = (html.match(/interactive-widget-container/g) || []).length;
    expect(containerCount).toBe(1);
  });

  test('creates one container per unique key via extract()', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('[Widget: a] texto [Widget: b] otro [Widget: a] repetido', state);

    var html = bodyDiv.children[0].innerHTML;
    var containerCount = (html.match(/interactive-widget-container/g) || []).length;
    expect(containerCount).toBe(2);
  });

  test('calls extract() with widget markers intact', function() {
    var extractCalls = [];
    var origExtract = global.KairosWidgets.extract;
    global.KairosWidgets.extract = function(text) {
      extractCalls.push(text);
      return origExtract(text);
    };

    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('antes [Widget: foo] despues', state);

    expect(extractCalls.length).toBe(1);
    expect(extractCalls[0]).toContain('[Widget: foo]');

    global.KairosWidgets.extract = origExtract;
  });

  test('does NOT call initAll()', function() {
    var initAllCalled = false;
    global.KairosWidgets.initAll = function() { initAllCalled = true; };

    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('[Widget: foo]', state);

    expect(initAllCalled).toBe(false);
  });

  test('renders text-only messages correctly', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('Hello world, no widgets here', state);

    expect(bodyDiv.children.length).toBe(1);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
    expect(bodyDiv.children[0].innerHTML).toContain('Hello world');
  });

  test('renders incomplete widget as escaped code', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('before ```html-widget\n<div>incomplete', state);

    expect(bodyDiv.children[0].innerHTML).toContain('<code>');
    expect(bodyDiv.children[0].innerHTML).toContain('```html-widget');
  });

  test('creates msg-text-segment for each phase', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('Phase 0 content', state);

    expect(bodyDiv.children.length).toBe(1);
    expect(bodyDiv.children[0].className).toBe('msg-text-segment');
  });

  test('accumulates tokens across calls', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('Hello ', state);
    handlingStream._cb('World', state);

    expect(state.contentTexts[0]).toBe('Hello World');
    expect(bodyDiv.children[0].innerHTML).toContain('Hello World');
  });

  test('handles html-widget code block', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    handlingStream._cb('Text ```html-widget\n<div>widget</div>\n``` more', state);

    var html = bodyDiv.children[0].innerHTML;
    var containerCount = (html.match(/interactive-widget-container/g) || []).length;
    expect(containerCount).toBe(1);
    expect(Object.keys(global.KairosWidgets.registry).length).toBe(1);
  });
});
