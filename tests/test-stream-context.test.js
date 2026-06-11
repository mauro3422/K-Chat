import { describe, test, expect, beforeEach } from 'vitest';
import './setup.js';

class MockElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.className = '';
    this.children = [];
    this.dataset = {};
    this.innerHTML = '';
    this._textContent = '';
    this.style = {};
    this.attributes = {};
    this.parentNode = null;
  }
  get textContent() { return this._textContent; }
  set textContent(v) { this._textContent = v; }
  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    return child;
  }
  removeChild(child) {
    var idx = this.children.indexOf(child);
    if (idx >= 0) this.children.splice(idx, 1);
  }
  get lastChild() { return this.children[this.children.length - 1] || null; }
  querySelector(sel) {
    if (sel === '.msg-body') {
      var body = new MockElement('div');
      body.className = 'msg-body';
      this.children.push(body);
      return body;
    }
    return null;
  }
  querySelectorAll(sel) { return []; }
  insertAdjacentElement(pos, el) {
    this.children.push(el);
    el.parentNode = this;
  }
  setAttribute(name, val) { this.attributes[name] = val; }
  getAttribute(name) { return this.attributes[name] || null; }
  classList = {
    _classes: [],
    add(c) { this._classes.push(c); },
    remove(c) { this._classes = this._classes.filter(x => x !== c); },
    contains(c) { return this._classes.includes(c); }
  };
  remove() {}
}

global.document = {
  createElement: (tag) => new MockElement(tag),
  querySelector: () => null,
  querySelectorAll: () => [],
};

const { StreamContext } = await import('../web/static/modules/stream-context.js');

describe('StreamContext', () => {

  function makeAsstDiv() {
    var el = new MockElement('div');
    el.querySelector = function(sel) {
      if (sel === '.msg-body') {
        if (!this._msgBody) {
          this._msgBody = new MockElement('div');
          this._msgBody.className = 'msg-body';
          this.children.push(this._msgBody);
        }
        return this._msgBody;
      }
      return null;
    };
    return el;
  }

  test('constructor requires asstDiv', () => {
    expect(() => new StreamContext(null)).toThrow('asstDiv is required');
    expect(() => new StreamContext(undefined)).toThrow('asstDiv is required');
  });

  test('initializes with defaults', () => {
    var asstDiv = makeAsstDiv();
    var ctx = new StreamContext(asstDiv);

    expect(ctx.getBodyDivs()).toHaveLength(1);
    expect(ctx.getContentText(0)).toBe('');
    expect(ctx.getReasoningEls()).toHaveLength(0);
    expect(ctx.getReasoningText()).toBe('');
    expect(ctx.getToolPhase()).toBe(0);
    expect(ctx.isFirstToken()).toBe(true);
    expect(ctx.getAsstDiv()).toBe(asstDiv);
  });

  test('getBodyDivs returns array with initial body', () => {
    var asstDiv = makeAsstDiv();
    var ctx = new StreamContext(asstDiv);
    var divs = ctx.getBodyDivs();
    expect(Array.isArray(divs)).toBe(true);
    expect(divs.length).toBe(1);
  });

  test('getContentText returns empty string for unset phase', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.getContentText(0)).toBe('');
    expect(ctx.getContentText(5)).toBe('');
  });

  test('setContentText and getContentText work', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.setContentText(0, 'hello');
    expect(ctx.getContentText(0)).toBe('hello');
    ctx.setContentText(1, 'world');
    expect(ctx.getContentText(1)).toBe('world');
  });

  test('appendContentText accumulates text', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.appendContentText(0, 'Hello ');
    ctx.appendContentText(0, 'World');
    ctx.appendContentText(0, '!');
    expect(ctx.getContentText(0)).toBe('Hello World!');
  });

  test('appendContentText creates entries for missing phases', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.appendContentText(2, 'Phase 2');
    expect(ctx.getContentText(2)).toBe('Phase 2');
    expect(ctx.getContentText(0)).toBe('');
    expect(ctx.getContentText(1)).toBe('');
  });

  test('reasoning text getter/setter', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.setReasoningText('thinking...');
    expect(ctx.getReasoningText()).toBe('thinking...');
  });

  test('appendReasoningText accumulates', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.appendReasoningText('Step 1');
    ctx.appendReasoningText(' Step 2');
    expect(ctx.getReasoningText()).toBe('Step 1 Step 2');
  });

  test('getReasoningState returns ReasoningState instance', () => {
    var ctx = new StreamContext(makeAsstDiv());
    var rs = ctx.getReasoningState();
    expect(rs).toBeDefined();
    expect(typeof rs.enter).toBe('function');
    expect(typeof rs.exit).toBe('function');
    expect(rs.isActive).toBe(false);
  });

  test('enterReasoningPhase activates reasoning state', () => {
    var ctx = new StreamContext(makeAsstDiv());
    var first = ctx.enterReasoningPhase();
    expect(first).toBe(true);
    expect(ctx.isReasoningActive()).toBe(true);
    var second = ctx.enterReasoningPhase();
    expect(second).toBe(false);
  });

  test('exitReasoningPhase deactivates reasoning state', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.enterReasoningPhase();
    expect(ctx.isReasoningActive()).toBe(true);
    ctx.exitReasoningPhase();
    expect(ctx.isReasoningActive()).toBe(false);
  });

  test('markToolTurn sets tool turn flag', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.getToolTurnSinceLastContent()).toBe(false);
    ctx.markToolTurn();
    expect(ctx.getToolTurnSinceLastContent()).toBe(true);
  });

  test('enterToolPhase increments phase only after tool turn', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.getToolPhase()).toBe(0);

    var phase1 = ctx.enterToolPhase();
    expect(phase1).toBe(0);
    expect(ctx.getToolPhase()).toBe(0);

    ctx.markToolTurn();
    var phase2 = ctx.enterToolPhase();
    expect(phase2).toBe(1);
    expect(ctx.getToolPhase()).toBe(1);

    ctx.markToolTurn();
    var phase3 = ctx.enterToolPhase();
    expect(phase3).toBe(2);
    expect(ctx.getToolPhase()).toBe(2);
  });

  test('getPhaseIndex computes correct index', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.getPhaseIndex()).toBe(0);

    ctx.addReasoningEl(new MockElement('details'));
    expect(ctx.getPhaseIndex()).toBe(0);

    ctx.addReasoningEl(new MockElement('details'));
    expect(ctx.getPhaseIndex()).toBe(1);

    ctx.addReasoningEl(new MockElement('details'));
    expect(ctx.getPhaseIndex()).toBe(2);

    ctx.markToolTurn();
    ctx.enterToolPhase();
    expect(ctx.getPhaseIndex()).toBe(3);
  });

  test('ensureBodyDiv creates new body divs', () => {
    var asstDiv = makeAsstDiv();
    var ctx = new StreamContext(asstDiv);
    expect(ctx.getBodyDivs()).toHaveLength(1);

    ctx.ensureBodyDiv(1, 'msg-body md-content');
    expect(ctx.getBodyDivs()).toHaveLength(2);

    ctx.ensureBodyDiv(0, 'msg-body md-content');
    expect(ctx.getBodyDivs()).toHaveLength(2);
  });

  test('addReasoningEl and getLastReasoningEl', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.getLastReasoningEl()).toBeNull();

    var el1 = new MockElement('details');
    ctx.addReasoningEl(el1);
    expect(ctx.getLastReasoningEl()).toBe(el1);

    var el2 = new MockElement('details');
    ctx.addReasoningEl(el2);
    expect(ctx.getLastReasoningEl()).toBe(el2);
    expect(ctx.getReasoningEls()).toHaveLength(2);
  });

  test('getWidgetCache returns per-phase cache', () => {
    var ctx = new StreamContext(makeAsstDiv());
    var cache0 = ctx.getWidgetCache(0);
    cache0.foo = 'bar';
    expect(ctx.getWidgetCache(0).foo).toBe('bar');

    var cache1 = ctx.getWidgetCache(1);
    expect(cache1.foo).toBeUndefined();
  });

  test('getWidgetMap returns per-phase map', () => {
    var ctx = new StreamContext(makeAsstDiv());
    var map0 = ctx.getWidgetMap(0);
    map0.key1 = 'val1';
    expect(ctx.getWidgetMap(0).key1).toBe('val1');

    var map1 = ctx.getWidgetMap(1);
    expect(map1.key1).toBeUndefined();
  });

  test('isFirstToken and clearFirstToken', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.isFirstToken()).toBe(true);
    ctx.clearFirstToken();
    expect(ctx.isFirstToken()).toBe(false);
  });

  test('reset clears all state', () => {
    var asstDiv = makeAsstDiv();
    var ctx = new StreamContext(asstDiv);

    ctx.appendContentText(0, 'hello');
    ctx.appendContentText(1, 'world');
    ctx.setReasoningText('thinking');
    ctx.enterReasoningPhase();
    ctx.markToolTurn();
    ctx.enterToolPhase();
    ctx.addReasoningEl(new MockElement('details'));
    ctx.clearFirstToken();
    ctx.getWidgetCache(0).foo = 'bar';

    ctx.reset();

    expect(ctx.getContentText(0)).toBe('');
    expect(ctx.getReasoningText()).toBe('');
    expect(ctx.isReasoningActive()).toBe(false);
    expect(ctx.getToolPhase()).toBe(0);
    expect(ctx.isFirstToken()).toBe(true);
    expect(ctx.getReasoningEls()).toHaveLength(0);
    expect(ctx.getWidgetCache(0).foo).toBeUndefined();
  });

  test('private fields are not directly accessible', () => {
    var ctx = new StreamContext(makeAsstDiv());
    expect(ctx.bodyDivs).toBeUndefined();
    expect(ctx.contentTexts).toBeUndefined();
    expect(ctx.asstDiv).toBeUndefined();
    expect(ctx._toolPhase).toBeUndefined();
  });

  test('no direct property mutation possible', () => {
    var ctx = new StreamContext(makeAsstDiv());
    ctx.bodyDivs = [];
    ctx.contentTexts = [];
    ctx._toolPhase = 100;

    expect(ctx.getBodyDivs()).toHaveLength(1);
    expect(ctx.getContentText(0)).toBe('');
    expect(ctx.getToolPhase()).toBe(0);
  });

  test('backwards compatible with state-like access via methods', () => {
    var asstDiv = makeAsstDiv();
    var ctx = new StreamContext(asstDiv);

    var bodyDivs = ctx.getBodyDivs();
    var contentTexts = [];
    for (var i = 0; i < bodyDivs.length; i++) {
      contentTexts.push(ctx.getContentText(i));
    }
    var reasoningEls = ctx.getReasoningEls();
    var reasoningState = ctx.getReasoningState();
    var asstDivRef = ctx.getAsstDiv();

    expect(bodyDivs).toHaveLength(1);
    expect(contentTexts[0]).toBe('');
    expect(reasoningEls).toHaveLength(0);
    expect(typeof reasoningState.enter).toBe('function');
    expect(asstDivRef).toBe(asstDiv);
  });

});
