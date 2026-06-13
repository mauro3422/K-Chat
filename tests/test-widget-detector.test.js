import { describe, test, expect, beforeEach, vi } from 'vitest';
import './setup.js';

var contentCallbacks = [];
var emittedEvents = [];

var mockStream = {
  _listeners: {},
  on: function(evt, cb) {
    if (evt === 'content') contentCallbacks.push(cb);
  },
  emit: function(evt, data) {
    if (evt === 'widget:detected') emittedEvents.push(data);
  }
};

vi.mock('../web/static/modules/stream-dispatcher.js', function() {
  return { KairosStream: mockStream };
});

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
    querySelector(sel) { return null; },
    querySelectorAll(sel) { return []; },
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
      contains: function(c) { return this._classes.indexOf(c) >= 0; }
    },
    remove: function() {}
  };
  return el;
}

describe('Widget Detector', function() {
  beforeEach(function() {
    contentCallbacks.length = 0;
    emittedEvents.length = 0;
    global.logUI = function() {};
  });

  function loadDetector() {
    vi.resetModules();
    return import('../web/static/modules/widgets/widget-detector.js');
  }

  test('detects [Widget: key] tag and emits event', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['Hello [Widget: dashboard] world'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('Hello [Widget: dashboard] world', state); });

    expect(emittedEvents.length).toBe(1);
    expect(emittedEvents[0].key).toBe('dashboard');
    expect(emittedEvents[0].code).toBe('');
    expect(emittedEvents[0].phaseIdx).toBe(0);
    expect(emittedEvents[0].bodyDiv).toBe(bodyDiv);
  });

  test('detects html-widget code block and emits event', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['Text ```html-widget\n<div>hi</div>\n``` more'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('Text ```html-widget\n<div>hi</div>\n``` more', state); });

    expect(emittedEvents.length).toBe(1);
    expect(emittedEvents[0].key).toBe(null);
    expect(emittedEvents[0].code).toBe('<div>hi</div>');
    expect(emittedEvents[0].phaseIdx).toBe(0);
  });

  test('detects html-widget with key', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['```html-widget my-widget\n<p>test</p>\n```'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('```html-widget my-widget\n<p>test</p>\n```', state); });

    expect(emittedEvents.length).toBe(1);
    expect(emittedEvents[0].key).toBe('my-widget');
    expect(emittedEvents[0].code).toBe('<p>test</p>');
  });

  test('does not create DOM elements', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var initialChildren = bodyDiv.children.length;
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['[Widget: foo] ```html-widget\n<div>x</div>\n``` [Widget: bar]'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('[Widget: foo] ```html-widget\n<div>x</div>\n``` [Widget: bar]', state); });

    expect(bodyDiv.children.length).toBe(initialChildren);
    expect(emittedEvents.length).toBe(3);
  });

  test('does not populate KairosWidgets.registry', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['```html-widget\n<div>x</div>\n```'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('```html-widget\n<div>x</div>\n```', state); });

    expect(emittedEvents.length).toBe(1);
  });

  test('deduplicates same key tags', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['[Widget: foo] and [Widget: foo] again'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('[Widget: foo] and [Widget: foo] again', state); });

    expect(emittedEvents.length).toBe(1);
    expect(emittedEvents[0].key).toBe('foo');
  });

  test('emits separate events for different keys', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['[Widget: a] text [Widget: b]'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('[Widget: a] text [Widget: b]', state); });

    expect(emittedEvents.length).toBe(2);
    expect(emittedEvents[0].key).toBe('a');
    expect(emittedEvents[1].key).toBe('b');
  });

  test('does not emit for same widget on repeated calls (cache)', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: [''],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    state.contentTexts[0] = '[Widget: foo]';
    contentCallbacks.forEach(function(cb) { cb('[Widget: foo]', state); });
    expect(emittedEvents.length).toBe(1);

    contentCallbacks.forEach(function(cb) { cb(' more text', state); });
    expect(emittedEvents.length).toBe(1);
  });

  test('handles multiple phases correctly', async function() {
    await loadDetector();

    var body0 = makeEl('div');
    var body1 = makeEl('div');
    var state = {
      bodyDivs: [body0, body1],
      contentTexts: ['', ''],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    state.contentTexts[0] = '[Widget: phase0]';
    contentCallbacks.forEach(function(cb) { cb('[Widget: phase0]', state); });

    state._toolPhase = 1;
    state.contentTexts[1] = '[Widget: phase1]';
    contentCallbacks.forEach(function(cb) { cb('[Widget: phase1]', state); });

    expect(emittedEvents.length).toBe(2);
    expect(emittedEvents[0].phaseIdx).toBe(0);
    expect(emittedEvents[0].bodyDiv).toBe(body0);
    expect(emittedEvents[1].phaseIdx).toBe(1);
    expect(emittedEvents[1].bodyDiv).toBe(body1);
  });

  test('gracefully handles missing state', async function() {
    await loadDetector();

    contentCallbacks.forEach(function(cb) { cb('text', null); });
    contentCallbacks.forEach(function(cb) { cb('text', {}); });

    expect(emittedEvents.length).toBe(0);
  });

  test('gracefully handles missing bodyDivs', async function() {
    await loadDetector();

    var state = {
      contentTexts: ['[Widget: foo]'],
      reasoningEls: []
    };

    contentCallbacks.forEach(function(cb) { cb('[Widget: foo]', state); });

    expect(emittedEvents.length).toBe(0);
  });

  test('does not emit for incomplete widget code block', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: ['```html-widget\n<div>incomplete'],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    contentCallbacks.forEach(function(cb) { cb('```html-widget\n<div>incomplete', state); });

    expect(emittedEvents.length).toBe(0);
  });

  test('emits when incomplete widget completes', async function() {
    await loadDetector();

    var bodyDiv = makeEl('div');
    var state = {
      bodyDivs: [bodyDiv],
      contentTexts: [''],
      reasoningEls: [],
      _toolPhase: 0,
      _toolTurnSinceLastContent: false
    };

    state.contentTexts[0] = '```html-widget\n<div>hi</div>';
    contentCallbacks.forEach(function(cb) { cb('```html-widget\n<div>hi</div>', state); });
    expect(emittedEvents.length).toBe(0);

    state.contentTexts[0] = '```html-widget\n<div>hi</div>\n```';
    contentCallbacks.forEach(function(cb) { cb('\n```', state); });
    expect(emittedEvents.length).toBe(1);
    expect(emittedEvents[0].code).toBe('<div>hi</div>');
  });
});
