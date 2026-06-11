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
    getAttribute(name) { return this.attributes[name] || this.dataset[name.replace('data-', '')] || null; },
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

global.document = {
  getElementById: function() { return null; },
  querySelector: function() { return null; },
  querySelectorAll: function() { return []; },
  createElement: function(tag) { return makeEl(tag); },
  addEventListener: function() {},
  body: { appendChild: function() {} },
  _listeners: {}
};

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
  global.KairosWidgets = {
    index: 0,
    nextIndex: function() { return this.index++; },
    registry: {},
    initAll: function() {},
    reset: function() {},
    debug: {}
  };
  global.DOMPurify = { sanitize: function(t) { return t; } };
  global.KairosMarkdown = { parse: function(t) { return '<p>' + t + '</p>'; } };
  global.logUI = function() {};
});

describe('Content Handler', function() {
  test('creates single widget container for duplicate marker in text', function() {
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
      _toolTurnSinceLastContent: false,
      _widgetCache: {},
      widgetMap: []
    };

    handlingStream._cb('[Widget: foo] y otro [Widget: foo] en el mismo texto', state);

    var containers = bodyDiv.querySelectorAll('.interactive-widget-container');
    expect(containers.length).toBe(1);

    bodyDiv.children.forEach(function(child) {
      if (child.className && child.className.indexOf('msg-text-segment') >= 0) {
        expect(child.innerHTML).not.toContain('interactive-widget-container');
      }
    });
  });

  test('creates one container per unique key', function() {
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
      _toolTurnSinceLastContent: false,
      _widgetCache: {},
      widgetMap: []
    };

    handlingStream._cb('[Widget: a] texto [Widget: b] otro [Widget: a] repetido', state);

    var containers = bodyDiv.querySelectorAll('.interactive-widget-container');
    expect(containers.length).toBe(2);
  });

  test('creates placeholder for duplicate key across phases', function() {
    var asstDiv = makeEl('div');
    var body0 = makeEl('div');
    body0.className = 'msg-body md-content';
    var body1 = makeEl('div');
    body1.className = 'msg-body md-content';
    asstDiv.appendChild(body0);
    asstDiv.appendChild(body1);

    var state = {
      bodyDivs: [body0, body1],
      asstDiv: asstDiv,
      contentTexts: ['', ''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false,
      _widgetCache: { 0: {}, 1: {} },
      widgetMap: []
    };

    handlingStream._cb('Fase 1 [Widget: dashboard]', state);

    state._toolPhase = 1;
    handlingStream._cb('Fase 2 [Widget: dashboard]', state);

    var containersInPhase1 = body1.querySelectorAll('.interactive-widget-container');
    expect(containersInPhase1.length).toBe(0);

    var placeholders = body1.children.filter(function(c) {
      return c.className && c.className.indexOf('widget-placeholder') >= 0;
    });
    expect(placeholders.length).toBe(1);
  });

  test('markers stripped from markdown parse input', function() {
    var asstDiv = makeEl('div');
    var bodyDiv = makeEl('div');
    bodyDiv.className = 'msg-body md-content';
    asstDiv.appendChild(bodyDiv);

    var parseTexts = [];
    global.KairosMarkdown.parse = function(text) {
      parseTexts.push(text);
      return '<p>' + text + '</p>';
    };

    var state = {
      bodyDivs: [bodyDiv],
      asstDiv: asstDiv,
      contentTexts: [''],
      reasoningEls: [],
      reasoningState: { exit: function() {} },
      _toolPhase: 0,
      _toolTurnSinceLastContent: false,
      _widgetCache: {},
      widgetMap: []
    };

    handlingStream._cb('antes [Widget: foo] despues', state);

    parseTexts.forEach(function(text) {
      expect(text).not.toContain('[Widget');
      expect(text).not.toMatch(/\[Widget:?\s*\w+\]/);
    });
  });
});
