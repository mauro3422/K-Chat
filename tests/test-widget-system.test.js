import { describe, test, expect } from 'vitest';
import './setup.js';

global.document = { getElementById: () => null, querySelector: () => null, querySelectorAll: () => [] };
global.window = { addEventListener: () => {}, widgetStates: {} };
global.logUI = () => {};
global.sessionId = 'test';
global.fetch = () => Promise.resolve();

const widgetsDir = new URL('../web/static/modules/widgets/', import.meta.url).pathname;
const coreModule = await import(`file://${widgetsDir}/core.js`);
const KairosWidgets = coreModule.KairosWidgets;
const iframeBuilder = await import(`file://${widgetsDir}/iframe-builder.js`);
const buildIframeSrc = iframeBuilder.buildIframeSrc;
await import(`file://${widgetsDir}/toolbar.js`);
await import(`file://${widgetsDir}/iframe.js`);
await import(`file://${widgetsDir}/messaging.js`);
await import(`file://${widgetsDir}/index.js`);

describe('Widget System', () => {
  test('extract genera IDs únicos', () => {
    const r1 = KairosWidgets.extract('```html-widget\n<div>A</div>\n```');
    const r2 = KairosWidgets.extract('```html-widget\n<div>B</div>\n```');
    expect(r1).toContain('widget-0');
    expect(r2).toContain('widget-1');
  });

  test('registry tiene widgets', () => {
    expect(Object.keys(KairosWidgets.registry).length).toBeGreaterThanOrEqual(2);
  });

  test('sanitizes ?.style', () => {
    const keys = Object.keys(KairosWidgets.registry);
    expect(KairosWidgets.registry[keys[0]].indexOf('?.style')).toBe(-1);
  });

  test('sanitizes ?.prop', () => {
    KairosWidgets.extract('```html-widget\nobj?.foo.bar = 42;\n```');
    const k = Object.keys(KairosWidgets.registry);
    expect(KairosWidgets.registry[k[k.length - 1]]).toContain('obj.foo.bar = 42');
  });

  test('preserves ?.classList', () => {
    KairosWidgets.extract('```html-widget\nif (el?.classList) { x(); }\n```');
    const k = Object.keys(KairosWidgets.registry);
    expect(KairosWidgets.registry[k[k.length - 1]]).toContain('el?.classList');
  });

  test('no widgets unchanged', () => {
    expect(KairosWidgets.extract('just text')).toBe('just text');
  });

  test('unclosed widget creates placeholder', () => {
    const r = KairosWidgets.extract('before\n```html-widget\n<p>hi</p>\nsome content');
    expect(r).toContain('interactive-widget-container');
  });

  test('multiple widgets in registry', () => {
    KairosWidgets.extract('```html-widget\n<a/>\n```\ntext\n```html-widget\n<b/>\n```');
    expect(Object.keys(KairosWidgets.registry).length).toBeGreaterThanOrEqual(6);
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
    KairosWidgets.log('w-x', 'init', 'detail');
    expect(KairosWidgets.debug['w-x']).toBeDefined();
    expect(KairosWidgets.debug['w-x'].events.length).toBe(1);
    expect(KairosWidgets.debug['w-x'].events[0].label).toBe('init');
    expect(KairosWidgets.debug['w-x'].events[0].detail).toBe('detail');
  });

  test('log appends events', () => {
    KairosWidgets.log('w-x', 'altura', '200px');
    expect(KairosWidgets.debug['w-x'].events.length).toBe(2);
  });

  test('reset clears registry and index', () => {
    KairosWidgets.reset();
    expect(Object.keys(KairosWidgets.registry).length).toBe(0);
    expect(KairosWidgets.index).toBe(0);
  });

  test('navigation cycle: extract → reset → re-extract', () => {
    KairosWidgets.reset();
    const rA = KairosWidgets.extract('```html-widget\n<div>Widget A</div>\n```');
    expect(rA).toContain('widget-0');
    KairosWidgets.reset();
    expect(Object.keys(KairosWidgets.registry).length).toBe(0);
    expect(KairosWidgets.index).toBe(0);
    const rB = KairosWidgets.extract('```html-widget\n<div>Widget B</div>\n```');
    expect(rB).toContain('widget-0');
    expect(KairosWidgets.registry['widget-0']).toBe('<div>Widget B</div>');
  });
});
