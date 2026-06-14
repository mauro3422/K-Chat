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
const WidgetManager = coreModule.WidgetManager;
const iframeBuilderModule = await import(`file://${widgetsDir}/iframe-builder.js`);
const iframeModule = await import(`file://${widgetsDir}/iframe.js`);
const messagingModule = await import(`file://${widgetsDir}/messaging.js`);
await import(`file://${widgetsDir}/index.js`);
await import('../web/static/modules/markdown-renderer.js');
await import('../web/static/modules/stream-dispatcher.js');
await import('../web/static/modules/content-handler.js');
const chatFormModule = await import('../web/static/modules/chat-form.js');
const ChatForm = chatFormModule.ChatForm;

describe('Frontend Integration', () => {
  test('WidgetManager tiene extract', () => {
    expect(typeof WidgetManager.extract).toBe('function');
  });

  test('WidgetManager tiene initAll', () => {
    expect(typeof iframeModule.initAll).toBe('function');
  });

  test('WidgetManager tiene log', () => {
    expect(typeof WidgetManager.log).toBe('function');
  });

  test('WidgetManager tiene reset', () => {
    expect(typeof WidgetManager.reset).toBe('function');
  });

  test('WidgetManager tiene startMessageHandler', () => {
    expect(typeof messagingModule.startMessageHandler).toBe('function');
  });

  test('WidgetManager tiene buildIframeSrc', () => {
    expect(typeof iframeBuilderModule.buildIframeSrc).toBe('function');
  });

  test('MarkdownRenderer tiene parse', () => {
    expect(typeof MarkdownRenderer.parse).toBe('function');
  });

  test('StreamDispatcher tiene on', () => {
    expect(typeof StreamDispatcher.on).toBe('function');
  });

  test('StreamDispatcher tiene emit', () => {
    expect(typeof StreamDispatcher.emit).toBe('function');
  });

  test('ChatForm tiene init', () => {
    expect(typeof ChatForm.init).toBe('function');
  });

  test('ChatForm tiene retry', () => {
    expect(typeof ChatForm.retry).toBe('function');
  });

  test('extract genera placeholder y registra widget', () => {
    WidgetManager.reset();
    const extracted = WidgetManager.extract('```html-widget\n<div>Test</div>\n```');
    expect(extracted).toContain('interactive-widget-container');
    expect(Object.keys(WidgetManager.registry).length).toBeGreaterThan(0);
  });

  test('parse retorna string', () => {
    const parsed = MarkdownRenderer.parse('**bold**');
    expect(typeof parsed).toBe('string');
  });

  test('log crea entrada debug', () => {
    WidgetManager.log('test-widget', 'test-event', 'test-detail');
    expect(WidgetManager.debug['test-widget']).toBeDefined();
    expect(WidgetManager.debug['test-widget'].events.length).toBeGreaterThan(0);
  });
});
