/**
 * Tests de integración para el sistema de chat frontend
 * Simula el flujo completo: submit → stream → render
 */

global.document = {
  getElementById: () => null,
  querySelector: () => null,
  querySelectorAll: () => [],
  createElement: () => ({ classList: { add: () => {} }, appendChild: () => {}, style: { cssText: '' }, onclick: null, textContent: '', id: '' }),
  addEventListener: () => {},
  body: { appendChild: () => {} }
};
global.window = {
  addEventListener: () => {},
  widgetStates: {},
  IntersectionObserver: null,
  ResizeObserver: null,
  location: { pathname: '/' },
  history: { replaceState: () => {} }
};
global.logUI = () => {};
global.logStream = () => {};
global.sessionId = 'test-session';
global.defaultModel = 'test-model';
global.fetch = () => Promise.resolve({ body: { getReader: () => ({ read: () => Promise.resolve({ done: true }) }) } });
global.DOMPurify = { sanitize: (s) => s };
global.marked = { parse: (s) => s };

eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/utils.js', 'utf8'));
eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/widget-system.js', 'utf8'));
eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/markdown-renderer.js', 'utf8'));
eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/stream-dispatcher.js', 'utf8'));
eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/stream-renderer.js', 'utf8'));
eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/chat-form.js', 'utf8'));

var passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) { passed++; console.log('PASS: ' + name); }
  else { failed++; console.log('FAIL: ' + name + (detail ? ' — ' + detail : '')); }
}

// Test 1: KairosUtils existe y tiene métodos
assert('KairosUtils.escHtml existe', typeof KairosUtils.escHtml === 'function');
assert('KairosUtils.esc existe', typeof KairosUtils.esc === 'function');
assert('KairosUtils.showToast existe', typeof KairosUtils.showToast === 'function');
assert('KairosUtils.initGlobalErrorHandlers existe', typeof KairosUtils.initGlobalErrorHandlers === 'function');

// Test 2: KairosWidgets existe y tiene métodos
assert('KairosWidgets.extract existe', typeof KairosWidgets.extract === 'function');
assert('KairosWidgets.initAll existe', typeof KairosWidgets.initAll === 'function');
assert('KairosWidgets.log existe', typeof KairosWidgets.log === 'function');
assert('KairosWidgets.reset existe', typeof KairosWidgets.reset === 'function');
assert('KairosWidgets.startMessageHandler existe', typeof KairosWidgets.startMessageHandler === 'function');
assert('KairosWidgets.buildIframeSrc existe', typeof KairosWidgets.buildIframeSrc === 'function');

// Test 3: KairosMarkdown existe y tiene métodos
assert('KairosMarkdown.parse existe', typeof KairosMarkdown.parse === 'function');
assert('KairosMarkdown.renderAll existe', typeof KairosMarkdown.renderAll === 'function');

// Test 4: KairosStream existe y tiene métodos
assert('KairosStream.on existe', typeof KairosStream.on === 'function');
assert('KairosStream.emit existe', typeof KairosStream.emit === 'function');

// Test 5: KairosForm existe y tiene métodos
assert('KairosForm.init existe', typeof KairosForm.init === 'function');
assert('KairosForm.retry existe', typeof KairosForm.retry === 'function');

// Test 6: Flujo de extracción de widgets
var testText = '```html-widget\n<div>Test</div>\n```';
var extracted = KairosWidgets.extract(testText);
assert('extract: genera placeholder', extracted.indexOf('interactive-widget-container') >= 0);
assert('extract: registra widget', Object.keys(KairosWidgets.registry).length > 0);

// Test 7: Flujo de parseo de markdown
var parsed = KairosMarkdown.parse('**bold**');
assert('parse: retorna string', typeof parsed === 'string');

// Test 8: Flujo de logging de widgets
KairosWidgets.log('test-widget', 'test-event', 'test-detail');
assert('log: crea entrada debug', KairosWidgets.debug['test-widget'] !== undefined);
assert('log: registra evento', KairosWidgets.debug['test-widget'].events.length > 0);

// Test 9: showToast con tipos
try {
  KairosUtils.showToast('test', 'warning');
  KairosUtils.showToast('test', 'error');
  KairosUtils.showToast('test', 'info');
  KairosUtils.showToast('test', 'success');
  assert('showToast: acepta todos los tipos', true);
} catch (e) {
  assert('showToast: acepta todos los tipos', false, e.message);
}

// Test 10: escHtml funciona correctamente
var escaped = KairosUtils.escHtml('<script>alert("xss")</script>');
assert('escHtml: escapa < y >', escaped.indexOf('&lt;') >= 0 && escaped.indexOf('&gt;') >= 0);
assert('escHtml: escapa comillas', escaped.indexOf('&quot;') >= 0);

console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
