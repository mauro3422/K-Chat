/**
 * Stress test: aborto de stream + persistencia en frontend.
 *
 * Simula el escenario donde el usuario envia un mensaje,
 * el asistente empieza a responder, y en medio el usuario
 * envia OTRO mensaje (abortando el anterior).
 *
 * Verifica que:
 * 1. El primer mensaje del asistente NO se borra del DOM si ya tiene contenido
 * 2. El segundo flujo se inicia correctamente
 * 3. Hay exactamente 2 mensajes de usuario y 2 de asistente al final
 */

// Mock DOM realista
function createMockElement(tag) {
  var el = {
    tagName: tag,
    className: '',
    _innerHTML: '',
    get innerHTML() { return el._innerHTML; },
    set innerHTML(html) {
      el._innerHTML = html;
      el.children = [];
      // Parsear divs de nivel superior del HTML
      var idx = 0;
      while (idx < html.length) {
        var openStart = html.indexOf('<div', idx);
        if (openStart < 0) break;
        var openEnd = html.indexOf('>', openStart);
        if (openEnd < 0) break;
        var tagContent = html.slice(openStart + 4, openEnd);
        var child = createMockElement('div');
        // Extraer class
        var classMatch = tagContent.match(/class="([^"]*)"/);
        if (classMatch) child.className = classMatch[1];
        // Extraer id
        var idMatch = tagContent.match(/id="([^"]*)"/);
        if (idMatch) child.id = idMatch[1];
        // Encontrar el cierre correspondiente
        var depth = 1;
        var searchIdx = openEnd + 1;
        while (depth > 0 && searchIdx < html.length) {
          var nextOpen = html.indexOf('<div', searchIdx);
          var nextClose = html.indexOf('</div>', searchIdx);
          if (nextClose < 0) break;
          if (nextOpen >= 0 && nextOpen < nextClose) {
            depth++;
            searchIdx = nextOpen + 4;
          } else {
            depth--;
            if (depth === 0) {
              var inner = html.slice(openEnd + 1, nextClose);
              child.innerHTML = inner;
              el.children.push(child);
              child.parentNode = el;
              idx = nextClose + 6;
              break;
            }
            searchIdx = nextClose + 6;
          }
        }
        if (depth > 0) break;
      }
    },
    get textContent() {
      // Si tiene hijos, sumar sus textContent; sino, derivar de innerHTML
      if (el.children && el.children.length > 0) {
        var txt = '';
        for (var i = 0; i < el.children.length; i++) {
          txt += el.children[i].textContent || '';
        }
        return txt;
      }
      return el._innerHTML ? el._innerHTML.replace(/<[^>]+>/g, '') : '';
    },
    set textContent(val) {
      // Actualizar innerHTML para que el getter funcione
      el._innerHTML = String(val);
    },
    style: {},
    id: '',
    dataset: {},
    classList: {
      add: function(c) {
        if (el.className.indexOf(c) < 0) el.className += (el.className ? ' ' : '') + c;
      },
      remove: function(c) {
        el.className = el.className.replace(new RegExp('\\b' + c + '\\b', 'g'), '').replace(/\s+/g, ' ').trim();
      },
      contains: function(c) {
        return el.className.split(/\s+/).indexOf(c) >= 0;
      }
    },
    appendChild: function(c) {
      if (!el.children) el.children = [];
      el.children.push(c);
      if (c) c.parentNode = el;
    },
    removeChild: function(c) {
      if (!el.children) return;
      var idx = el.children.indexOf(c);
      if (idx >= 0) el.children.splice(idx, 1);
    },
    querySelector: function(s) {
      if (!el.children) return null;
      for (var i = 0; i < el.children.length; i++) {
        var child = el.children[i];
        if (s.startsWith('.')) {
          var classes = s.slice(1).split('.');
          if (child.className) {
            var childClasses = child.className.split(/\s+/);
            var allMatch = classes.every(function(c) { return childClasses.indexOf(c) >= 0; });
            if (allMatch) return child;
          }
        }
        if (s.startsWith('#') && child.id === s.slice(1)) return child;
        if (child.tagName && child.tagName.toLowerCase() === s.toLowerCase()) return child;
      }
      return null;
    },
    querySelectorAll: function(s) {
      var res = [];
      if (!el.children) return res;
      for (var i = 0; i < el.children.length; i++) {
        var child = el.children[i];
        if (s.startsWith('.')) {
          var classes = s.slice(1).split('.');
          if (child.className) {
            var childClasses = child.className.split(/\s+/);
            var allMatch = classes.every(function(c) { return childClasses.indexOf(c) >= 0; });
            if (allMatch) res.push(child);
          }
        } else if (s.startsWith('#') && child.id === s.slice(1)) {
          res.push(child);
        } else if (child.tagName && child.tagName.toLowerCase() === s.toLowerCase()) {
          res.push(child);
        }
      }
      return res;
    },
    setAttribute: function(k, v) { el[k] = v; },
    getAttribute: function(k) { return el[k]; },
    children: [],
    parentNode: null,
    insertAdjacentHTML: function(pos, html) {
      if (pos === 'beforeend') {
        console.log('insertAdjacentHTML called on', el.id || el.tagName, 'with html:', html.substring(0, 80));
        el._innerHTML += html;
        // Parsear y agregar solo los nuevos elementos, sin reemplazar children
        var idx = 0;
        var count = 0;
        while (idx < html.length) {
          var openStart = html.indexOf('<div', idx);
          if (openStart < 0) break;
          var openEnd = html.indexOf('>', openStart);
          if (openEnd < 0) break;
          var tagContent = html.slice(openStart + 4, openEnd);
          var child = createMockElement('div');
          var classMatch = tagContent.match(/class="([^"]*)"/);
          if (classMatch) child.className = classMatch[1];
          var idMatch = tagContent.match(/id="([^"]*)"/);
          if (idMatch) child.id = idMatch[1];
          var depth = 1;
          var searchIdx = openEnd + 1;
          while (depth > 0 && searchIdx < html.length) {
            var nextOpen = html.indexOf('<div', searchIdx);
            var nextClose = html.indexOf('</div>', searchIdx);
            if (nextClose < 0) break;
            if (nextOpen >= 0 && nextOpen < nextClose) {
              depth++;
              searchIdx = nextOpen + 4;
            } else {
              depth--;
              if (depth === 0) {
                var inner = html.slice(openEnd + 1, nextClose);
                child.innerHTML = inner;
                el.children.push(child);
                child.parentNode = el;
                count++;
                idx = nextClose + 6;
                break;
              }
              searchIdx = nextClose + 6;
            }
          }
          if (depth > 0) break;
        }
        console.log('  Added', count, 'children. Total:', el.children.length);
      }
    },
    insertAdjacentElement: function(pos, newEl) {
      if (pos === 'beforebegin') {
        if (el.parentNode && el.parentNode.children) {
          var idx = el.parentNode.children.indexOf(el);
          if (idx >= 0) {
            el.parentNode.children.splice(idx, 0, newEl);
            newEl.parentNode = el.parentNode;
          }
        }
      } else if (pos === 'afterend') {
        if (el.parentNode && el.parentNode.children) {
          var idx2 = el.parentNode.children.indexOf(el);
          if (idx2 >= 0) {
            el.parentNode.children.splice(idx2 + 1, 0, newEl);
            newEl.parentNode = el.parentNode;
          }
        }
      } else if (pos === 'beforeend') {
        el.appendChild(newEl);
      }
    },
    remove: function() {
      console.log('REMOVE called on', el.tagName, el.className, 'parent:', el.parentNode ? el.parentNode.id || el.parentNode.className : 'none');
      if (el.parentNode && el.parentNode.removeChild) {
        el.parentNode.removeChild(el);
      }
    },
    dispatchEvent: function(e) {
      if (el._listeners && el._listeners[e.type]) {
        el._listeners[e.type].forEach(function(fn) { fn(e); });
      }
      return !e.defaultPrevented;
    },
    addEventListener: function(type, fn) {
      if (!el._listeners) el._listeners = {};
      if (!el._listeners[type]) el._listeners[type] = [];
      el._listeners[type].push(fn);
    }
  };
  return el;
}

// Mock de Event
global.Event = function(type, opts) {
  this.type = type;
  this.cancelable = opts && opts.cancelable || false;
  this.bubbles = opts && opts.bubbles || false;
  this.defaultPrevented = false;
  this.target = null;
};
global.Event.prototype.preventDefault = function() {
  this.defaultPrevented = true;
};

// Mock de DOMException
global.DOMException = function(msg, name) {
  this.message = msg;
  this.name = name;
};
// TextEncoder para fetch mock — retorna Uint8Array real para TextDecoder
global.TextEncoder = function() {};
global.TextEncoder.prototype.encode = function(str) {
  return Buffer.from(str, 'utf8');
};

// Crear elementos mock
var mockMessages = createMockElement('div');
mockMessages.id = 'messages';
var _origAppendChild = mockMessages.appendChild.bind(mockMessages);
// Sobrescribir insertAdjacentHTML para que cree elementos reales
mockMessages.insertAdjacentHTML = function(pos, html) {
  if (pos === 'beforeend') {
    // Solo sumar al string, NO usar setter de innerHTML (reemplaza children)
    mockMessages._innerHTML += html;
    // Parsear y agregar el div de nivel superior
    var topDivRegex = /^<div\b[^>]*class="([^"]*)"[^>]*>([\s\S]*)<\/div>$/;
    var match = html.match(topDivRegex);
    if (match) {
      var el = createMockElement('div');
      el.className = match[1];
      el.innerHTML = match[2];
      mockMessages.appendChild(el);
    }
  }
};
// Instrumentar appendChild para debug
mockMessages.appendChild = function(c) {
  console.log('APPEND to messages:', c.tagName, c.className);
  _origAppendChild(c);
};

var mockInput = createMockElement('input');
mockInput.id = 'msg-input';
mockInput.value = '';
mockInput.disabled = false;
mockInput.focus = function() { console.log('input.focus() called'); };

var mockSpinner = createMockElement('div');
mockSpinner.id = 'spinner';
mockSpinner.textContent = '';

var mockForm = createMockElement('form');
mockForm.id = 'chat-form';

// Mock document con registry de event listeners
var _docListeners = {};
global.document = {
  getElementById: function(id) {
    if (id === 'messages') return mockMessages;
    if (id === 'msg-input') return mockInput;
    if (id === 'spinner') return mockSpinner;
    if (id === 'chat-form') return mockForm;
    return null;
  },
  querySelector: function(sel) {
    if (sel === '#chat-form') return mockForm;
    if (sel === '#msg-input') return mockInput;
    return null;
  },
  querySelectorAll: function(sel) {
    if (sel === '.msg.user') return mockMessages.querySelectorAll('.msg.user');
    if (sel === '.msg.assistant') return mockMessages.querySelectorAll('.msg.assistant');
    if (sel === '.tc-item.calling') return [];
    if (sel === '.tc-item.ok') return [];
    return [];
  },
  createElement: function(tag) {
    return createMockElement(tag);
  },
  addEventListener: function(type, fn) {
    if (!_docListeners[type]) _docListeners[type] = [];
    _docListeners[type].push(fn);
  },
  dispatchEvent: function(e) {
    e.target = e.target || this;
    var listeners = _docListeners[e.type] || [];
    listeners.forEach(function(fn) {
      try {
        fn(e);
      } catch(err) {
        console.error('Error en listener:', err.message, err.stack);
      }
    });
    return !e.defaultPrevented;
  },
  body: { appendChild: function() {} }
};

global.window = {
  addEventListener: function() {},
  widgetStates: {},
  IntersectionObserver: null,
  ResizeObserver: null,
  location: { pathname: '/' },
  history: { replaceState: function() {} }
};

global.logUI = function() {};
global.logStream = function() {};
global.sessionId = 'test-session';
global.defaultModel = 'test-model';
global.DOMPurify = { sanitize: function(s) { return s; } };
global.marked = { parse: function(s) { return s; } };

// Mock fetch controlable
var fetchCallCount = 0;

global.fetch = function(url, options) {
  fetchCallCount++;
  var callNum = fetchCallCount;
  var signal = options && options.signal;

  var chunks = [];
  var readerIndex = 0;

  if (callNum === 1) {
    // Primer stream: reasoning + contenido parcial, luego aborta
    chunks = [
      { done: false, value: new TextEncoder().encode('{"t":"reasoning","d":"Pensando..."}\n') },
      { done: false, value: new TextEncoder().encode('{"t":"content","d":"Hola "}\n') },
      { done: false, value: new TextEncoder().encode('{"t":"content","d":"mundo"}\n') },
      { abort: true }, // Simular que el siguiente read falla con AbortError
    ];
  } else {
    // Segundo stream: completo
    chunks = [
      { done: false, value: new TextEncoder().encode('{"t":"content","d":"Respuesta final."}\n') },
      { done: true, value: undefined },
    ];
  }

  var reader = {
    read: function() {
      return new Promise(function(resolve, reject) {
        if (signal && signal.aborted) {
          console.log('reader.read: rejecting because signal aborted');
          reject(new DOMException('Aborted', 'AbortError'));
          return;
        }
        if (readerIndex < chunks.length) {
          var chunk = chunks[readerIndex++];
          console.log('reader.read: chunk', readerIndex - 1, 'done=', chunk.done, 'value_len=', chunk.value ? chunk.value.length : 0);
          if (chunk.abort) {
            console.log('reader.read: rejecting with AbortError (simulated)');
            reject(new DOMException('Aborted', 'AbortError'));
            return;
          }
          resolve(chunk);
        } else {
          console.log('reader.read: resolving done=true');
          resolve({ done: true });
        }
      });
    }
  };

  return Promise.resolve({ body: { getReader: function() { return reader; } }, status: 200 });
};

// Cargar modulos del frontend
eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/modules/utils.js'), 'utf8'));
var widgetsDir = require('path').join(__dirname, '../web/static/modules/widgets');
eval(require('fs').readFileSync(require('path').join(widgetsDir, 'core.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(widgetsDir, 'iframe-builder.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(widgetsDir, 'toolbar.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(widgetsDir, 'iframe.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(widgetsDir, 'messaging.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(widgetsDir, 'index.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/modules/markdown-renderer.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/modules/stream-dispatcher.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/modules/stream-renderer.js'), 'utf8'));
eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/modules/chat-form.js'), 'utf8'));

// Asegurar que KairosWidgets esta disponible globalmente para KairosMarkdown.parse
if (!global.KairosWidgets && global.window && global.window.KairosWidgets) {
  global.KairosWidgets = global.window.KairosWidgets;
}

// Interceptar KairosStream.emit para debuggear
var _origEmit = KairosStream.emit;
console.log('_origEmit is:', typeof _origEmit);
console.log('Listeners before intercept:', Object.keys(KairosStream.listeners));
KairosStream.emit = function(event, data, state) {
  console.log('KairosStream.emit:', event, JSON.stringify(data).substring(0, 40), 'listeners:', (KairosStream.listeners[event] || []).length);
  if (typeof _origEmit !== 'function') {
    console.log('_origEmit is not a function!');
    return;
  }
  var start = Date.now();
  _origEmit.call(KairosStream, event, data, state);
  console.log('_origEmit returned in', Date.now() - start, 'ms');
  try {
    if (state && state.bodyDivs && state.bodyDivs[0]) {
      var bd = state.bodyDivs[0];
      console.log('After emit: bodyDiv.textContent =', JSON.stringify(bd.textContent), 'children:', bd.children.length);
    } else {
      console.log('After emit: no bodyDivs');
    }
  } catch(e) {
    console.log('Error in emit intercept:', e.message);
  }
};

var passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) { passed++; console.log('PASS: ' + name); }
  else { failed++; console.log('FAIL: ' + name + (detail ? ' — ' + detail : '')); }
}

// Inicializar formulario
KairosForm.init();

console.log('\n--- Test de stress: aborto de stream ---');

// Test 1: Enviar primer mensaje
console.log('Enviando primer mensaje...');
console.log('Listeners registrados:', Object.keys(_docListeners));
mockInput.value = 'Hola Kairos';
var event1 = new Event('submit', { cancelable: true, bubbles: true });
event1.target = mockForm;
document.dispatchEvent(event1);
console.log('Evento disparado, esperando async...');

setTimeout(function() {
  console.log('Estado despues del primer mensaje:');
  console.log('messages.innerHTML:', mockMessages.innerHTML.substring(0, 200));
  console.log('messages.children.length:', mockMessages.children.length);
  for (var ci = 0; ci < mockMessages.children.length; ci++) {
    console.log('  child[' + ci + ']: tag=' + mockMessages.children[ci].tagName + ' class=' + mockMessages.children[ci].className);
  }
  var asstMsgs1 = mockMessages.querySelectorAll('.msg.assistant');
  var userMsgs1 = mockMessages.querySelectorAll('.msg.user');
  console.log('  Asistente: ' + asstMsgs1.length + ', Usuario: ' + userMsgs1.length);

  assert('primer envio: 1 msg usuario', userMsgs1.length === 1, userMsgs1.length);
  assert('primer envio: 1 msg asistente', asstMsgs1.length === 1, asstMsgs1.length);

  // Verificar que el asistente existe
  var firstAsst = asstMsgs1[0];
  assert('primer asistente: div existe', firstAsst !== null);

  // Test 2: Enviar segundo mensaje (aborta el primero)
  console.log('Enviando segundo mensaje (aborta el primero)...');
  mockInput.value = 'Otra pregunta';
  var event2 = new Event('submit', { cancelable: true, bubbles: true });
  event2.target = mockForm;
  document.dispatchEvent(event2);

  setTimeout(function() {
    console.log('Estado despues del segundo mensaje:');
    var asstMsgs2 = mockMessages.querySelectorAll('.msg.assistant');
    var userMsgs2 = mockMessages.querySelectorAll('.msg.user');
    console.log('  Asistente: ' + asstMsgs2.length + ', Usuario: ' + userMsgs2.length);

    // Verificaciones clave del bug
    assert('segundo envio: 2 msgs usuario', userMsgs2.length === 2, userMsgs2.length);
    assert('segundo envio: 2 msgs asistente', asstMsgs2.length === 2, asstMsgs2.length);

    // El primer asistente NO debe haber sido borrado
    assert('primer asistente: NO fue borrado', asstMsgs2.length === 2, 'se borro el mensaje anterior');

    // El segundo asistente debe existir
    var secondAsst = asstMsgs2[1];
    assert('segundo asistente: existe', secondAsst !== null);

    // fetch debe haber sido llamado 2 veces
    assert('fetch llamado 2 veces', fetchCallCount === 2, fetchCallCount);

    console.log('\n' + passed + ' passed, ' + failed + ' failed');
    process.exit(failed > 0 ? 1 : 0);
  }, 300);
}, 300);
