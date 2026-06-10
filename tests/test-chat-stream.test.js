import { describe, test, expect, beforeEach } from 'vitest';
import './setup.js';

// Override chat-stream specific mocks
const _utils = { escHtml: (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') };
const _widgets = { startMessageHandler() { _widgets._startCalled = true; }, reset() {}, debug: {} };
const _form = { init() { _form._initCalled = true; }, reset() {}, retry() {} };

global.window = {
  addEventListener: () => {},
  widgetStates: {},
  location: { pathname: '/' },
  history: { replaceState(state, title, url) { global.window._lastState = state; global.window._lastUrl = url; } },
  KairosUtils: _utils,
  KairosWidgets: _widgets,
  KairosForm: _form
};
global.KairosUtils = _utils;
global.KairosWidgets = _widgets;
global.KairosForm = _form;
global.sessionId = 'chat-stream-sid';
global.defaultModel = 'test-model';
global.KairosMarkdown = { renderAll() {} };
global.KairosStream = { on() {}, emit() {} };
global.fetch = () => Promise.resolve({ text: () => Promise.resolve('<div id="messages">content</div>') });
global.logUI = () => {};
global.logStream = () => {};

await import('../web/static/chat-stream.js');

describe('chat-stream', () => {
  test('retryLastMessage es function', () => {
    expect(typeof window.retryLastMessage).toBe('function');
  });

  test('escHtml es function', () => {
    expect(typeof window.escHtml).toBe('function');
  });

  test('escHtml escapa < > & "', () => {
    const result = window.escHtml('<b>test & "comillas"</b>');
    expect(result).toBe('&lt;b&gt;test &amp; &quot;comillas&quot;&lt;/b&gt;');
  });

  test('widgetStates es object', () => {
    expect(typeof window.widgetStates).toBe('object');
  });

  test('loadSession cambia sessionId', () => {
    const prevSid = global.sessionId;
    global.fetch = () => Promise.resolve({ text: () => Promise.resolve('') });
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('custom-sid-999');
    expect(global.sessionId).toBe('custom-sid-999');
    global.sessionId = prevSid;
  });

  test('loadSession llama replaceState', () => {
    global.fetch = () => Promise.resolve({ text: () => Promise.resolve('') });
    global.document.getElementById = () => ({ innerHTML: '' });
    window._lastState = undefined;
    window._lastUrl = undefined;
    window.loadSession('sid-replace-test');
    expect(window._lastState).toBeDefined();
    expect(window._lastState.sid).toBe('sid-replace-test');
    expect(window._lastUrl).toContain('sid-replace-test');
  });

  test('loadSession pasa URL correcta', () => {
    global.fetch = () => Promise.resolve({ text: () => Promise.resolve('') });
    global.document.getElementById = () => ({ innerHTML: '' });
    window._lastUrl = undefined;
    window.loadSession('url-test-sid');
    expect(window._lastUrl).toContain('url-test-sid');
  });

  test('loadSession llama widgets.reset', () => {
    let wReset = false;
    global.KairosWidgets.reset = () => { wReset = true; };
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('sid-reset');
    expect(wReset).toBe(true);
  });

  test('loadSession llama form.reset', () => {
    let fReset = false;
    global.KairosForm.reset = () => { fReset = true; };
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('sid-reset');
    expect(fReset).toBe(true);
  });

  test('DOMContentLoaded con /sessions/ invoca loadSession', () => {
    global.window.location.pathname = '/sessions/abc-123';
    let loaded = false;
    const origLoad = window.loadSession;
    window.loadSession = () => { loaded = true; };
    const handler = global.document._listeners?.DOMContentLoaded;
    if (handler) handler();
    window.loadSession = origLoad;
    expect(loaded).toBe(true);
  });

  test('DOMContentLoaded con / no invoca loadSession', () => {
    global.window.location.pathname = '/';
    let loaded = false;
    const origLoad = window.loadSession;
    window.loadSession = () => { loaded = true; };
    const handler = global.document._listeners?.DOMContentLoaded;
    if (handler) handler();
    window.loadSession = origLoad;
    expect(loaded).toBe(false);
  });

  test('startMessageHandler ejecutado al cargar', () => {
    expect(_widgets._startCalled).toBe(true);
  });

  test('KairosForm.init ejecutado al cargar', () => {
    expect(_form._initCalled).toBe(true);
  });

  test('loadSession llama fetch con URL correcta', async () => {
    let fetchedUrl = null;
    global.fetch = (url) => { fetchedUrl = url; return Promise.resolve({ text: () => Promise.resolve('') }); };
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('url-test-sid');
    expect(fetchedUrl).toBe('/sessions/url-test-sid/messages');
  });

  test('loadSession llama renderAll', async () => {
    let renderCalled = false;
    global.KairosMarkdown = { renderAll: () => { renderCalled = true; } };
    const fetchPromise = Promise.resolve({ text: () => Promise.resolve('<div id="messages"></div>') });
    global.fetch = () => fetchPromise;
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('render-test-sid');
    await fetchPromise;
    await new Promise(r => setTimeout(r, 10));
    expect(renderCalled).toBe(true);
  });
});
