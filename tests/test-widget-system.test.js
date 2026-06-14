import { describe, test, expect } from 'vitest';
import './setup.js';

global.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [], addEventListener: () => {}, createElement: () => ({ className: '', dataset: {}, innerHTML: '', style: {}, children: [], appendChild: function() {}, removeChild: function() {}, classList: { add: function() {} } }) };
global.window = { addEventListener: () => {}, widgetStates: {} };
global.logUI = () => {};
global.sessionId = 'test';
global.fetch = () => Promise.resolve();

const widgetsDir = new URL('../web/static/modules/widgets/', import.meta.url).pathname;
const coreModule = await import(`file://${widgetsDir}/core.js`);
const WidgetManager = coreModule.WidgetManager;
const iframeBuilder = await import(`file://${widgetsDir}/iframe-builder.js`);
const buildIframeSrc = iframeBuilder.buildIframeSrc;
const iframeModule = await import(`file://${widgetsDir}/iframe.js`);
await import(`file://${widgetsDir}/messaging.js`);
await import(`file://${widgetsDir}/index.js`);
const { setWidgetObserver } = iframeModule;

describe('Widget System', () => {
  test('extract genera IDs únicos', () => {
    const r1 = WidgetManager.extract('```html-widget\n<div>A</div>\n```');
    const r2 = WidgetManager.extract('```html-widget\n<div>B</div>\n```');
    expect(r1).toContain('widget-0');
    expect(r2).toContain('widget-1');
  });

  test('registry tiene widgets', () => {
    expect(Object.keys(WidgetManager.registry).length).toBeGreaterThanOrEqual(2);
  });

  test('sanitizes ?.style', () => {
    const keys = Object.keys(WidgetManager.registry);
    expect(WidgetManager.registry[keys[0]].indexOf('?.style')).toBe(-1);
  });

  test('sanitizes ?.prop', () => {
    WidgetManager.extract('```html-widget\nobj?.foo.bar = 42;\n```');
    const k = Object.keys(WidgetManager.registry);
    expect(WidgetManager.registry[k[k.length - 1]]).toContain('obj.foo.bar = 42');
  });

  test('preserves ?.classList', () => {
    WidgetManager.extract('```html-widget\nif (el?.classList) { x(); }\n```');
    const k = Object.keys(WidgetManager.registry);
    expect(WidgetManager.registry[k[k.length - 1]]).toContain('el?.classList');
  });

  test('no widgets unchanged', () => {
    expect(WidgetManager.extract('just text')).toBe('just text');
  });

  test('unclosed widget creates placeholder', () => {
    const r = WidgetManager.extract('before\n```html-widget\n<p>hi</p>\nsome content');
    expect(r).toContain('interactive-widget-container');
  });

  test('multiple widgets in registry', () => {
    WidgetManager.extract('```html-widget\n<a/>\n```\ntext\n```html-widget\n<b/>\n```');
    expect(Object.keys(WidgetManager.registry).length).toBeGreaterThanOrEqual(6);
  });

  test('buildIframeSrc has required elements', () => {
    const src = buildIframeSrc('w-test', '<p>hi</p>', 'null');
    expect(src).toContain('<p>hi</p>');
    expect(src).toContain('sendHeight');
    expect(src).toContain('ResizeObserver');
    expect(src).toContain('saveState');
    expect(src).toContain('"w-test"');
    expect(src).toContain('initialState');
  });

  test('log creates debug entry', () => {
    WidgetManager.log('w-x', 'init', 'detail');
    expect(WidgetManager.debug['w-x']).toBeDefined();
    expect(WidgetManager.debug['w-x'].events.length).toBe(1);
    expect(WidgetManager.debug['w-x'].events[0].label).toBe('init');
    expect(WidgetManager.debug['w-x'].events[0].detail).toBe('detail');
  });

  test('log appends events', () => {
    WidgetManager.log('w-x', 'altura', '200px');
    expect(WidgetManager.debug['w-x'].events.length).toBe(2);
  });

  test('reset clears registry and index', () => {
    WidgetManager.reset();
    expect(Object.keys(WidgetManager.registry).length).toBe(0);
    expect(WidgetManager.index).toBe(0);
  });

  test('navigation cycle: extract → reset → re-extract', () => {
    WidgetManager.reset();
    const rA = WidgetManager.extract('```html-widget\n<div>Widget A</div>\n```');
    expect(rA).toContain('widget-0');
    WidgetManager.reset();
    expect(Object.keys(WidgetManager.registry).length).toBe(0);
    expect(WidgetManager.index).toBe(0);
    const rB = WidgetManager.extract('```html-widget\n<div>Widget B</div>\n```');
    expect(rB).toContain('widget-0');
    expect(WidgetManager.registry['widget-0']).toBe('<div>Widget B</div>');
  });

  test('initAll logs init only once per container in lazy mode', () => {
    WidgetManager.reset();
    var container = {
      dataset: {},
      attributes: {},
      children: [],
      getAttribute: function(name) {
        var m = { 'data-widget-id': 'w-lazy-test', 'data-widget-key': 'ltk1' };
        return m[name] || null;
      },
      setAttribute: function(name, val) { this.attributes[name] = val; if (name.startsWith('data-')) this.dataset[name.slice(5)] = val; },
      classList: { contains: function() { return false; } },
      appendChild: function() { },
      removeChild: function() { },
      offsetHeight: 0,
      parentElement: null
    };
    var scope = {
      className: 'msg-body',
      querySelectorAll: function(sel) {
        if (sel === '.interactive-widget-container') return [container];
        return [];
      }
    };

    setWidgetObserver({ observe: function() {} });
    iframeModule.initAll(scope);
    iframeModule.initAll(scope);

    var widget = WidgetManager.debug['w-lazy-test'];
    expect(widget).toBeDefined();
    var inits = widget.events.filter(function(e) { return e.label === 'init'; });
    expect(inits.length).toBe(1);
  });
});
