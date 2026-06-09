// Mocking global environment
global.logUI = () => {};
global.KairosWidgets = {
  index: 0,
  registry: {},
  initAll: () => {}
};
global.KairosMarkdown = {
  parse: (t) => '<p>' + t + '</p>'
};
global.KairosUtils = {
  escHtml: (t) => t
};
global.DOMPurify = {
  sanitize: (t) => t
};

class MockElement {
  constructor(tag) {
    this.tagName = tag.toUpperCase();
    this.className = '';
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.innerHTML = '';
    this._textContent = '';
  }

  get textContent() {
    return this._textContent;
  }

  set textContent(val) {
    this._textContent = val;
    if (val === '') {
      this.children = [];
    }
  }

  get lastChild() {
    return this.children[this.children.length - 1];
  }

  get classList() {
    const self = this;
    return {
      contains: (cls) => self.className.split(/\s+/).indexOf(cls) >= 0
    };
  }

  appendChild(el) {
    el.parentNode = this;
    this.children.push(el);
    return el;
  }

  removeChild(el) {
    const idx = this.children.indexOf(el);
    if (idx >= 0) {
      this.children.splice(idx, 1);
      el.parentNode = null;
    }
    return el;
  }

  insertBefore(newEl, refEl) {
    const idx = this.children.indexOf(refEl);
    if (idx >= 0) {
      this.children.splice(idx, 0, newEl);
      newEl.parentNode = this;
    } else {
      this.appendChild(newEl);
    }
    return newEl;
  }

  setAttribute(name, val) {
    this.attributes[name] = val;
  }

  getAttribute(name) {
    return this.attributes[name];
  }

  querySelectorAll(sel) {
    const res = [];
    const traverse = (node) => {
      for (const child of node.children) {
        if (sel === '.interactive-widget-container' && child.className === 'interactive-widget-container') {
          res.push(child);
        } else if (sel === '.msg-text-segment' && child.className === 'msg-text-segment') {
          res.push(child);
        }
        traverse(child);
      }
    };
    traverse(this);
    return res;
  }
}

global.document = {
  createElement: (tag) => new MockElement(tag)
};

// Event Emitter Mock for KairosStream
const listeners = {};
global.KairosStream = {
  on: (evt, cb) => {
    listeners[evt] = cb;
  },
  emit: (evt, ...args) => {
    if (listeners[evt]) listeners[evt](...args);
  }
};

// Load stream-renderer.js
eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/stream-renderer.js', 'utf8'));

let passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) {
    passed++;
    console.log('PASS: ' + name);
  } else {
    failed++;
    console.log('FAIL: ' + name + (detail ? ' — ' + detail : ''));
  }
}

// 1. Test TypeError Protection and initialization
const state = {
  asstDiv: new MockElement('div'),
  bodyDivs: [new MockElement('div')],
  reasoningEls: [],
  contentTexts: [''],
  reasoningText: '',
  firstToken: false
};

// Se llama a content con un token
try {
  KairosStream.emit('content', 'Hola ', state);
  assert('safely initializes widgetMap', state.widgetMap !== undefined);
  assert('safely initializes phase index inside widgetMap', state.widgetMap[0] !== undefined);
} catch (e) {
  assert('safely initializes widgetMap without throwing', false, e.message + '\n' + e.stack);
}

// 2. Test segment sync during stream
// Vamos a emitir una secuencia de tokens simulando la generación de un widget
KairosStream.emit('content', 'Este es un widget:\n```html-widget\n<div>Contenido Widget</div>\n```\nTexto final.', state);

const bodyDiv = state.bodyDivs[0];
assert('bodyDiv children length is 3 (TextSegment 0, Widget 0, TextSegment 1)', bodyDiv.children.length === 3, `children length = ${bodyDiv.children.length}`);
assert('Child 0 is a text segment', bodyDiv.children[0].className === 'msg-text-segment');
assert('Child 1 is a widget container', bodyDiv.children[1].className === 'interactive-widget-container');
assert('Child 2 is a text segment', bodyDiv.children[2].className === 'msg-text-segment');

assert('Child 1 data-widget-id is widget-0', bodyDiv.children[1].getAttribute('data-widget-id') === 'widget-0');
assert('Widget registered in KairosWidgets', KairosWidgets.registry['widget-0'] === '<div>Contenido Widget</div>');

// 3. Test caching mechanism: second emit with same content should not change targetSeg.dataset.rawText
const prevRawText = bodyDiv.children[0].dataset.rawText;
KairosStream.emit('content', '', state); // Emitir token vacío
assert('Text segment cache key works', bodyDiv.children[0].dataset.rawText === prevRawText);

console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
