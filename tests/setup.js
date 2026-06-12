// Global DOM mocks for Vitest JS module testing

class MockElement {
  constructor(tag) {
    this.tagName = (tag || 'div').toUpperCase();
    this.className = '';
    this.children = [];
    this.dataset = {};
    this._innerHTML = '';
    this._textContent = '';
    this.style = {};
    this.onclick = null;
    this.onkeydown = null;
    this.attributes = {};
  }
  get textContent() { return this._textContent; }
  set textContent(v) { this._textContent = v; }
  get outerHTML() { return '<' + this.tagName + '>'; }
  appendChild(child) { this.children.push(child); child.parentNode = this; return child; }
  insertAdjacentElement(pos, el) {
    if (pos === 'beforebegin' && this.parentNode) {
      var p = this.parentNode;
      var idx = p.children.indexOf(this);
      if (idx >= 0) p.children.splice(idx, 0, el);
      else p.children.push(el);
      el.parentNode = p;
    } else if (pos === 'afterend' && this.parentNode) {
      var p = this.parentNode;
      var idx = p.children.indexOf(this);
      if (idx >= 0) p.children.splice(idx + 1, 0, el);
      else p.children.push(el);
      el.parentNode = p;
    } else {
      this.children.push(el);
      el.parentNode = this;
    }
    return el;
  }
  remove() {
    if (this.parentNode) {
      var idx = this.parentNode.children.indexOf(this);
      if (idx >= 0) this.parentNode.children.splice(idx, 1);
    }
  }
  get innerHTML() { return this._innerHTML; }
  set innerHTML(html) {
    this._innerHTML = html;
    this.children = [];
    var tagRe = /<(\w+)([^>]*)>([^<]*)<\/\1>/g;
    var attrRe = /(\w+)(?:="([^"]*)")?/g;
    var m;
    while ((m = tagRe.exec(html)) !== null) {
      var child = new MockElement(m[1]);
      var attrs = m[2];
      var text = m[3];
      var am;
      while ((am = attrRe.exec(attrs)) !== null) {
        if (am[1] === 'class' && am[2]) child.className = am[2];
        else if (am[2] !== undefined) child.setAttribute(am[1], am[2]);
      }
      if (text && text.trim()) child.textContent = text.trim();
      this.children.push(child);
      child.parentNode = this;
    }
  }
  querySelector(sel) {
    // [data-xxx="val"]
    var attrMatch = sel.match(/^\[data-(\w+)="([^"]*)"\]$/);
    if (attrMatch) {
      var attr = attrMatch[1], val = attrMatch[2];
      function search(node) {
        if (node.getAttribute('data-' + attr) === val || node.dataset[attr] === val) return node;
        for (var i = 0; i < node.children.length; i++) {
          var f = search(node.children[i]);
          if (f) return f;
        }
        return null;
      }
      return search(this);
    }
    if (sel.indexOf('.') === 0) {
      var cls = sel.substring(1);
      for (var i = 0; i < this.children.length; i++) {
        var c = this.children[i];
        if (c.className === cls || c.className.indexOf(cls + ' ') === 0 || c.className.indexOf(' ' + cls) >= 0) return c;
        var r = c.querySelector(sel);
        if (r) return r;
      }
      return null;
    }
    if (sel === 'summary' || sel === 'details' || sel === 'div' || sel === 'span') {
      var tag = sel.toUpperCase();
      for (var i = 0; i < this.children.length; i++) {
        if (this.children[i].tagName === tag) return this.children[i];
        var r = this.children[i].querySelector(sel);
        if (r) return r;
      }
      return null;
    }
    return null;
  }
  querySelectorAll(sel) {
    if (sel.indexOf('.') === 0) {
      var cls = sel.substring(1);
      var res = [];
      function walk(node) {
        for (var i = 0; i < node.children.length; i++) {
          var c = node.children[i];
          if (c.className === cls || c.className.indexOf(cls + ' ') === 0 || c.className.indexOf(' ' + cls) >= 0) res.push(c);
          walk(c);
        }
      }
      walk(this);
      return res;
    }
    return [];
  }
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

global.KairosUtils = { escHtml: (s) => String(s), scrollToBottom: () => {} };
global.KairosWidgets = {
  index: 0,
  nextIndex: function() { return this.index++; },
  registry: {},
  initAll: () => {},
  reset: () => {},
  startMessageHandler: () => {},
  debug: {},
};
global.KairosMarkdown = { parse: (t) => '<p>' + t + '</p>' };
global.KairosStream = { on: () => {}, emit: () => {} };
global.KairosForm = { init: () => {}, reset: () => {}, retry: () => {} };
global.DOMPurify = { sanitize: (t) => t };
global.logUI = () => {};
global.logStream = () => {};
