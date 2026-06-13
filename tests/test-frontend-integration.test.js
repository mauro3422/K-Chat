import { describe, test, expect } from 'vitest';
import './setup.js';

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

const widgetsDir = new URL('../web/static/modules/widgets/', import.meta.url).pathname;
const coreModule = await import(`file://${widgetsDir}/core.js`);
const KairosWidgets = coreModule.KairosWidgets;
const iframeBuilderModule = await import(`file://${widgetsDir}/iframe-builder.js`);
const iframeModule = await import(`file://${widgetsDir}/iframe.js`);
const messagingModule = await import(`file://${widgetsDir}/messaging.js`);
await import(`file://${widgetsDir}/index.js`);
await import('../web/static/modules/markdown-renderer.js');
await import('../web/static/modules/stream-dispatcher.js');
await import('../web/static/modules/content-handler.js');
const chatFormModule = await import('../web/static/modules/chat-form.js');
const KairosForm = chatFormModule.KairosForm;

describe('Frontend Integration', () => {
  test('KairosWidgets tiene extract', () => {
    expect(typeof KairosWidgets.extract).toBe('function');
  });

  test('KairosWidgets tiene initAll', () => {
    expect(typeof iframeModule.initAll).toBe('function');
  });

  test('KairosWidgets tiene log', () => {
    expect(typeof KairosWidgets.log).toBe('function');
  });

  test('KairosWidgets tiene reset', () => {
    expect(typeof KairosWidgets.reset).toBe('function');
  });

  test('KairosWidgets tiene startMessageHandler', () => {
    expect(typeof messagingModule.startMessageHandler).toBe('function');
  });

  test('KairosWidgets tiene buildIframeSrc', () => {
    expect(typeof iframeBuilderModule.buildIframeSrc).toBe('function');
  });

  test('KairosMarkdown tiene parse', () => {
    expect(typeof KairosMarkdown.parse).toBe('function');
  });

  test('KairosStream tiene on', () => {
    expect(typeof KairosStream.on).toBe('function');
  });

  test('KairosStream tiene emit', () => {
    expect(typeof KairosStream.emit).toBe('function');
  });

  test('KairosForm tiene init', () => {
    expect(typeof KairosForm.init).toBe('function');
  });

  test('KairosForm tiene retry', () => {
    expect(typeof KairosForm.retry).toBe('function');
  });

  test('extract genera placeholder y registra widget', () => {
    KairosWidgets.reset();
    const extracted = KairosWidgets.extract('```html-widget\n<div>Test</div>\n```');
    expect(extracted).toContain('interactive-widget-container');
    expect(Object.keys(KairosWidgets.registry).length).toBeGreaterThan(0);
  });

  test('parse retorna string', () => {
    const parsed = KairosMarkdown.parse('**bold**');
    expect(typeof parsed).toBe('string');
  });

  test('log crea entrada debug', () => {
    KairosWidgets.log('test-widget', 'test-event', 'test-detail');
    expect(KairosWidgets.debug['test-widget']).toBeDefined();
    expect(KairosWidgets.debug['test-widget'].events.length).toBeGreaterThan(0);
  });
});
