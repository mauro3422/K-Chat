global.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] };
global.window = { addEventListener: () => {}, widgetStates: {} };
global.logUI = () => {};
global.sessionId = 'test';
global.fetch = () => Promise.resolve();

eval(require('fs').readFileSync('C:/Dev/Kairos/web/static/modules/widget-system.js','utf8'));

var passed = 0, failed = 0;
function assert(name, cond, detail) {
  if (cond) { passed++; console.log('PASS: ' + name); }
  else { failed++; console.log('FAIL: ' + name + (detail ? ' — ' + detail : '')); }
}

// Test extract: unique IDs
var r1 = KairosWidgets.extract('```html-widget\n<div>A</div>\n```');
var r2 = KairosWidgets.extract('```html-widget\n<div>B</div>\n```');
assert('unique IDs', r1.indexOf('widget-0') >= 0 && r2.indexOf('widget-1') >= 0, r1 + ' | ' + r2);
assert('registry has 2', Object.keys(KairosWidgets.registry).length === 2);

// Test extract: sanitizes ?.style =
var keys = Object.keys(KairosWidgets.registry);
assert('sanitizes ?.style', KairosWidgets.registry[keys[0]].indexOf('?.style') < 0);

// Test extract: sanitizes ?.prop =
KairosWidgets.extract('```html-widget\nobj?.foo.bar = 42;\n```');
var k3 = Object.keys(KairosWidgets.registry);
assert('sanitizes ?.prop', KairosWidgets.registry[k3[2]].indexOf('obj.foo.bar = 42') >= 0);

// Test extract: preserves non-assignment optional chaining
KairosWidgets.extract('```html-widget\nif (el?.classList) { x(); }\n```');
var k4 = Object.keys(KairosWidgets.registry);
assert('preserves ?.classList', KairosWidgets.registry[k4[3]].indexOf('el?.classList') >= 0);

// Test extract: no widgets
var plain = KairosWidgets.extract('just text');
assert('no widgets unchanged', plain === 'just text');

// Test extract: container div placeholder
var r5 = KairosWidgets.extract('before\n```html-widget\n<p>hi</p>\n```\nafter');
assert('container div placeholder', r5.indexOf('interactive-widget-container') >= 0);
assert('preserves surrounding text', r5.indexOf('before') >= 0 && r5.indexOf('after') >= 0);

// Test extract: multiple widgets
var multi = KairosWidgets.extract('```html-widget\n<a/>\n```\ntext\n```html-widget\n<b/>\n```');
var multiKeys = Object.keys(KairosWidgets.registry);
assert('multiple widgets in registry', multiKeys.length >= 6);
assert('preserves text between', multi.indexOf('text') >= 0);

// Test buildIframeSrc
var src = KairosWidgets.buildIframeSrc('w-test', '<p>hi</p>', 'null');
assert('srcdoc has code', src.indexOf('<p>hi</p>') >= 0);
assert('srcdoc has sendHeight', src.indexOf('sendHeight') >= 0);
assert('srcdoc has CSS override', src.indexOf('auto!important') >= 0 || src.indexOf('auto !important') >= 0);
assert('srcdoc has 100vh', src.indexOf('[style*="100vh"]') >= 0);
assert('srcdoc has ResizeObserver', src.indexOf('ResizeObserver') >= 0);
assert('srcdoc has debounce', src.indexOf('_lastSentH') >= 0);
assert('srcdoc has onerror', src.indexOf('window.onerror') >= 0);
assert('srcdoc has saveState', src.indexOf('saveState') >= 0);
assert('srcdoc has widget ID', src.indexOf('"w-test"') >= 0);
assert('srcdoc has initialState', src.indexOf('initialState') >= 0);

// Test log
KairosWidgets.log('w-x', 'init', 'detail');
assert('log creates entry', KairosWidgets.debug['w-x'] !== undefined);
assert('log event count', KairosWidgets.debug['w-x'].events.length === 1);
assert('log event label', KairosWidgets.debug['w-x'].events[0].label === 'init');
assert('log event detail', KairosWidgets.debug['w-x'].events[0].detail === 'detail');
KairosWidgets.log('w-x', 'altura', '200px');
assert('log appends', KairosWidgets.debug['w-x'].events.length === 2);

console.log('\n' + passed + ' passed, ' + failed + ' failed');
process.exit(failed > 0 ? 1 : 0);
