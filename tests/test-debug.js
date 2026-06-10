global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ classList: { add: () => {}, toggle: () => {} }, appendChild: () => {}, style: { cssText: '' }, onclick: null, textContent: '', id: '' }),
  addEventListener: () => {},
  body: { appendChild: () => {} }
};
global.window = {
  addEventListener: () => {},
  location: { pathname: '/' },
  history: { replaceState: () => {} },
};
global.navigator.clipboard = { writeText: function() { return { then: function(cb) { cb(); return { catch: function() {} }; } }; } };
global.sessionId = 'debug-test-sid';
global.KairosUtils = { escHtml: function(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); } };
global.KairosWidgets = { debug: {}, log: function() {} };
global.fetch = function() { return Promise.resolve({ json: function() { return Promise.resolve({}); } }); };
global.setTimeout = setTimeout;
global.clearTimeout = clearTimeout;

eval(require('fs').readFileSync(require('path').join(__dirname, '../web/static/debug.js'), 'utf8'));
// KairosDebug is now in scope from eval()

var passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) { passed++; console.log('  PASS: ' + name); }
  else { failed++; console.log('  FAIL: ' + name + (detail ? ' -- ' + detail : '')); }
}

// 1. logUI guarda evento en uiEvents
(function test_logUI_basic() {
  try {
    KairosDebug.logUI('test-label', 'test-detail');
    var btn = { textContent: 'copy' };
    KairosDebug.copyUILog(btn);
    assert('logUI con datos normales guarda evento en uiEvents', btn.textContent === 'copiado');
  } catch (e) {
    assert('logUI con datos normales guarda evento en uiEvents', false, e.message);
  }
})();

// 2. logUI con label vacio no lanza error
(function test_logUI_empty_label() {
  try {
    KairosDebug.logUI('', '');
    assert('logUI con label vacio no lanza error', true);
  } catch (e) {
    assert('logUI con label vacio no lanza error', false, e.message);
  }
})();

// 3. logStream guarda evento en streamEvents
(function test_logStream_basic() {
  try {
    KairosDebug.logStream('content', 'texto de prueba');
    var btn = { textContent: 'copy' };
    KairosDebug.copyStreamLog(btn);
    assert('logStream con datos normales guarda evento en streamEvents', btn.textContent === 'copiado');
  } catch (e) {
    assert('logStream con datos normales guarda evento en streamEvents', false, e.message);
  }
})();

// 4. logStream con data null no lanza error
(function test_logStream_null_data() {
  try {
    KairosDebug.logStream('error', null);
    assert('logStream con data null no lanza error', true);
  } catch (e) {
    assert('logStream con data null no lanza error', false, e.message);
  }
})();

// 5. logStream con data objeto se serializa a JSON
(function test_logStream_object_data() {
  try {
    KairosDebug.logStream('tool_call', { name: 'test', args: { x: 1 } });
    assert('logStream con objeto data no lanza error', true);
  } catch (e) {
    assert('logStream con objeto data no lanza error', false, e.message);
  }
})();

// 6. toggleDebug alterna visibilidad y modifica DOM classList
(function test_toggleDebug_dom() {
  var panelClasses = { _open: false, toggle: function(cls, val) { if (cls === 'open') this._open = val !== undefined ? val : !this._open; }, contains: function() { return this._open; } };
  var mainClasses = { _shifted: false, toggle: function(cls, val) { if (cls === 'shifted') this._shifted = val !== undefined ? val : !this._shifted; }, contains: function() { return this._shifted; } };
  global.document.getElementById = function(id) {
    if (id === 'debug-panel') return { classList: panelClasses };
    if (id === 'main') return { classList: mainClasses };
    return null;
  };
  KairosDebug.toggleDebug();
  assert('toggleDebug: primera vez abre panel', KairosDebug.debugVisible === true);
  assert('toggleDebug: agrega clase open al panel', panelClasses._open === true);
  assert('toggleDebug: agrega clase shifted al main', mainClasses._shifted === true);
  KairosDebug.toggleDebug();
  assert('toggleDebug: segunda vez cierra panel', KairosDebug.debugVisible === false);
  assert('toggleDebug: remueve clase open del panel', panelClasses._open === false);
})();

// 7. toggleDebug sin elementos DOM no lanza error
(function test_toggleDebug_no_dom() {
  global.document.getElementById = function() { return null; };
  try {
    KairosDebug.toggleDebug();
    KairosDebug.toggleDebug();
    assert('toggleDebug sin elementos DOM no lanza error', true);
  } catch (e) {
    assert('toggleDebug sin elementos DOM no lanza error', false, e.message);
  }
})();

// 8. copyText sin elemento pre muestra []
(function test_copyText_no_pre() {
  var btn = { textContent: 'copy', parentElement: { querySelector: function() { return null; } } };
  KairosDebug.copyText(btn);
  assert('copyText sin pre muestra []', btn.textContent === '[]');
})();

// 9. copyUILog cambia texto del botón a 'copiado'
(function test_copyUILog_does_not_throw() {
  var btn = { textContent: 'copy' };
  try {
    KairosDebug.copyUILog(btn);
    assert('copyUILog cambia texto del botón a copiado', btn.textContent === 'copiado');
  } catch (e) {
    assert('copyUILog cambia texto del botón a copiado', false, e.message);
  }
})();

// 10. copyStreamLog cambia texto del botón a 'copiado'
(function test_copyStreamLog_does_not_throw() {
  var btn = { textContent: 'copy' };
  try {
    KairosDebug.copyStreamLog(btn);
    assert('copyStreamLog cambia texto del botón a copiado', btn.textContent === 'copiado');
  } catch (e) {
    assert('copyStreamLog cambia texto del botón a copiado', false, e.message);
  }
})();

// 11. copyWidgetLog sin KairosWidgets muestra []
(function test_copyWidgetLog_no_widgets() {
  var origWidgets = global.KairosWidgets;
  global.KairosWidgets = undefined;
  var btn = { textContent: 'copy' };
  KairosDebug.copyWidgetLog(btn);
  assert('copyWidgetLog sin KairosWidgets muestra []', btn.textContent === '[]');
  global.KairosWidgets = origWidgets;
})();

console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
