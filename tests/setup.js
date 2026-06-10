// Global DOM mocks for Vitest JS module testing

class MockElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.className = '';
    this.children = [];
    this.dataset = {};
    this.innerHTML = '';
    this._textContent = '';
    this.style = {};
    this.onclick = null;
    this.onkeydown = null;
    this.attributes = {};
  }
  get textContent() { return this._textContent; }
  set textContent(v) { this._textContent = v; }
  get outerHTML() { return '<' + this.tagName + '>'; }
  appendChild(child) { this.children.push(child); return child; }
  insertAdjacentElement(pos, el) { this.children.push(el); return el; }
  remove() {}
  querySelector(sel) { return null; }
  querySelectorAll(sel) { return []; }
  getAttribute(name) { return this.attributes[name] || this.dataset[name] || null; }
  setAttribute(name, val) { this.attributes[name] = val; }
  closest(sel) { return null; }
  classList = {
    _classes: [],
    add(c) { this._classes.push(c); },
    remove(c) { this._classes = this._classes.filter(x => x !== c); },
    toggle(c, force) {
      if (force === undefined) force = !this._classes.includes(c);
      if (force) { if (!this._classes.includes(c)) this._classes.push(c); }
      else { this._classes = this._classes.filter(x => x !== c); }
      return force;
    },
    contains(c) { return this._classes.includes(c); }
  };
}

global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: (tag) => new MockElement(tag),
  addEventListener: (evt, cb) => {
    global.document._listeners = global.document._listeners || {};
    global.document._listeners[evt] = cb;
  },
  body: { appendChild: () => {} },
};

global.window = {
  addEventListener: () => {},
  location: { pathname: '/', href: '' },
  history: { replaceState: () => {}, pushState: () => {} },
  navigator: { clipboard: { writeText: () => Promise.resolve() } },
};

global.fetch = () => Promise.resolve({ text: () => Promise.resolve(''), json: () => Promise.resolve({}) });
global.sessionId = 'test-session';
global.defaultModel = 'test-model';
global.debugVisible = false;
global.toggleDebug = () => {};

global.KairosUtils = { escHtml: (s) => String(s), scrollToBottom: () => {} };
global.KairosWidgets = {
  index: 0,
  nextIndex: function() { return this.index++; },
  registry: {},
  initAll: () => {},
  reset: () => {},
  debug: {},
};
global.KairosMarkdown = { parse: (t) => '<p>' + t + '</p>' };
global.KairosStream = { on: () => {}, emit: () => {} };
global.KairosForm = { init: () => {}, reset: () => {}, retry: () => {} };
global.DOMPurify = { sanitize: (t) => t };
global.logUI = () => {};
global.logStream = () => {};
