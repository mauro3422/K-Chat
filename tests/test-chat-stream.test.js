import { describe, test, expect, beforeEach, vi } from 'vitest';
import './setup.js';

vi.mock('../web/static/modules/markdown-renderer.js', () => ({
  KairosMarkdown: { renderAll: vi.fn() }
}));

// Override chat-stream specific mocks
const _utils = { escHtml: (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') };

global.KairosUtils = _utils;
global.sessionId = 'chat-stream-sid';
global.defaultModel = 'test-model';
global.KairosStream = { on() {}, emit() {} };
global.fetch = () => Promise.resolve({ text: () => Promise.resolve('<div id="messages">content</div>') });
global.logUI = () => {};
global.logStream = () => {};

// Set up window with history mock before importing chat-stream.js
global.window = Object.assign(global.window || {}, {
  addEventListener: () => {},
  widgetStates: {},
  location: { pathname: '/' },
  history: { replaceState(state, title, url) { global.window._lastState = state; global.window._lastUrl = url; } },
  KairosUtils: _utils
});

var chatModule = await import('../web/static/chat-stream.js');

// Ensure KairosForm and KairosWidgets have mock reset/retry
global.window.KairosForm = Object.assign(global.window.KairosForm || {}, { reset() {}, retry() {} });
global.window.KairosWidgets = Object.assign(global.window.KairosWidgets || {}, { reset() {} });
global.KairosForm = global.window.KairosForm;
global.KairosWidgets = global.window.KairosWidgets;

describe('chat-stream', () => {

  test('sessionId configurado', () => {
    expect(global.sessionId).toBe('chat-stream-sid');
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

  test('loadSession definida', () => {
    expect(typeof window.loadSession).toBe('function');
  });

  test('loadSession llama fetch con URL correcta', async () => {
    let fetchedUrl = null;
    global.fetch = (url) => { fetchedUrl = url; return Promise.resolve({ text: () => Promise.resolve('') }); };
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('url-test-sid');
    expect(fetchedUrl).toBe('/sessions/url-test-sid/messages');
  });

  test('loadSession llama renderAll', async () => {
    const { KairosMarkdown } = await import('../web/static/modules/markdown-renderer.js');
    const fetchPromise = Promise.resolve({ text: () => Promise.resolve('<div id="messages"></div>') });
    global.fetch = () => fetchPromise;
    global.document.getElementById = () => ({ innerHTML: '' });
    window.loadSession('render-test-sid');
    await fetchPromise;
    await new Promise(r => setTimeout(r, 10));
    expect(KairosMarkdown.renderAll).toHaveBeenCalled();
  });
});
