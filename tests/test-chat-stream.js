global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ classList: { add: () => {} }, appendChild: () => {}, style: { cssText: '' }, onclick: null, textContent: '', id: '' }),
  addEventListener: (evt, cb) => { global.document._listeners = global.document._listeners || {}; global.document._listeners[evt] = cb; },
  body: { appendChild: () => {} }
};
var _utils = { escHtml: function(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); } };
var _widgets = { startMessageHandler: function() { _widgets._startCalled = true; }, reset: function() {}, debug: {} };
var _form = { init: function() { _form._initCalled = true; }, reset: function() {}, retry: function() {} };
global.window = {
  addEventListener: () => {},
  widgetStates: {},
  location: { pathname: '/' },
  history: { replaceState: function(state, title, url) { global.window._lastState = state; global.window._lastUrl = url; } },
  KairosUtils: _utils,
  KairosWidgets: _widgets,
  KairosForm: _form
};
global.KairosUtils = _utils;
global.KairosWidgets = _widgets;
global.KairosForm = _form;
global.sessionId = 'chat-stream-sid';
global.defaultModel = 'test-model';
global.KairosMarkdown = { renderAll: function() {} };
global.KairosStream = { on: function() {}, emit: function() {} };
global.fetch = function() { return Promise.resolve({ text: function() { return Promise.resolve('<div id="messages">content</div>'); } }); };
global.logUI = function() {};
global.logStream = function() {};
var _origConsoleLog = console.log;
var _origConsoleError = console.error;
console.error = function() {};

eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/chat-stream.js'), 'utf8'));

var passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) { passed++; console.log('  PASS: ' + name); }
  else { failed++; console.log('  FAIL: ' + name + (detail ? ' -- ' + detail : '')); }
}

// 1. window.retryLastMessage esta definido
(function test_retryLastMessage_defined() {
  assert('retryLastMessage es function', typeof window.retryLastMessage === 'function');
})();

// 2. window.escHtml esta definido
(function test_escHtml_defined() {
  assert('escHtml es function', typeof window.escHtml === 'function');
})();

// 3. window.escHtml escapa caracteres HTML
(function test_escHtml_escapes() {
  var result = window.escHtml('<b>test & "comillas"</b>');
  assert('escHtml escapa < > & "', result === '&lt;b&gt;test &amp; &quot;comillas&quot;&lt;/b&gt;', result);
})();

// 4. window.widgetStates se inicializa como objeto
(function test_widgetStates_initialized() {
  assert('widgetStates es object', typeof window.widgetStates === 'object');
})();

// 5. loadSession cambia sessionId global (sync)
(function test_loadSession_changes_sid() {
  var prevSid = global.sessionId;
  global.fetch = function() { return Promise.resolve({ text: function() { return Promise.resolve(''); } }); };
  global.document.getElementById = function() { return { innerHTML: '' }; };
  window.loadSession('custom-sid-999');
  assert('loadSession cambia sessionId sincronicamente', global.sessionId === 'custom-sid-999');
  global.sessionId = prevSid;
})();

// 6. loadSession llama history.replaceState (sync)
(function test_loadSession_calls_replaceState() {
  global.fetch = function() { return Promise.resolve({ text: function() { return Promise.resolve(''); } }); };
  global.document.getElementById = function() { return { innerHTML: '' }; };
  window._lastState = undefined;
  window._lastUrl = undefined;
  window.loadSession('sid-replace-test');
  assert('loadSession llama replaceState con sid', window._lastState && window._lastState.sid === 'sid-replace-test');
  assert('loadSession pasa URL correcta', window._lastUrl && window._lastUrl.indexOf('sid-replace-test') >= 0);
})();

// 7. loadSession llama KairosWidgets.reset y KairosForm.reset (sync)
(function test_loadSession_calls_reset() {
  var wReset = false, fReset = false;
  global.KairosWidgets.reset = function() { wReset = true; };
  global.KairosForm.reset = function() { fReset = true; };
  global.document.getElementById = function() { return { innerHTML: '' }; };
  window.loadSession('sid-reset');
  assert('loadSession llama widgets.reset sincronicamente', wReset);
  assert('loadSession llama form.reset sincronicamente', fReset);
})();

// 8. DOMContentLoaded con path /sessions/ llama loadSession
(function test_DOMContentLoaded_sessions_path() {
  global.window.location.pathname = '/sessions/abc-123';
  var loaded = false;
  var origLoad = window.loadSession;
  window.loadSession = function() { loaded = true; };
  var handler = global.document._listeners && global.document._listeners.DOMContentLoaded;
  if (handler) handler();
  window.loadSession = origLoad;
  assert('DOMContentLoaded con /sessions/ invoca loadSession', loaded);
})();

// 9. DOMContentLoaded con path / NO llama loadSession
(function test_DOMContentLoaded_root_path() {
  global.window.location.pathname = '/';
  var loaded = false;
  var origLoad = window.loadSession;
  window.loadSession = function() { loaded = true; };
  var handler = global.document._listeners && global.document._listeners.DOMContentLoaded;
  if (handler) handler();
  window.loadSession = origLoad;
  assert('DOMContentLoaded con path / no invoca loadSession', !loaded);
})();

// 10. KairosWidgets.startMessageHandler fue llamado (ejecutado al cargar)
(function test_startMessageHandler_called() {
  assert('startMessageHandler ejecutado al cargar el modulo', global.KairosWidgets._startCalled === true);
})();

// 11. KairosForm.init fue llamado (ejecutado al cargar)
(function test_formInit_called() {
  assert('KairosForm.init ejecutado al cargar el modulo', global.KairosForm._initCalled === true);
})();

// 12. loadSession llama fetch con la URL correcta
(function test_loadSession_fetch_url() {
  var fetchedUrl = null;
  global.fetch = function(url) { fetchedUrl = url; return Promise.resolve({ text: function() { return Promise.resolve(''); } }); };
  global.document.getElementById = function() { return { innerHTML: '' }; };
  window.loadSession('url-test-sid');
  assert('loadSession llama fetch con URL /sessions/{sid}/messages', fetchedUrl === '/sessions/url-test-sid/messages');
})();

// 13. loadSession llama KairosMarkdown.renderAll() después de cargar (async)
var asyncPending = 1;
(function test_loadSession_calls_renderAll() {
  var renderCalled = false;
  global.KairosMarkdown = { renderAll: function() { renderCalled = true; } };
  var fetchPromise = Promise.resolve({ text: function() { return Promise.resolve('<div id="messages"></div>'); } });
  global.fetch = function() { return fetchPromise; };
  global.document.getElementById = function() { return { innerHTML: '' }; };
  window.loadSession('render-test-sid');
  fetchPromise.then(function() {}).then(function() {}).then(function() {}).then(function() {
    assert('loadSession llama KairosMarkdown.renderAll()', renderCalled);
    asyncPending--;
    if (asyncPending === 0) { console.log('\n' + passed + ' passed, ' + failed + ' failed'); process.exit(failed > 0 ? 1 : 0); }
  });
})();

if (asyncPending === 0) { console.log('\n' + passed + ' passed, ' + failed + ' failed'); process.exit(failed > 0 ? 1 : 0); }
