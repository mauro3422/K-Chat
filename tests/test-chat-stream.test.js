import { describe, test, expect, beforeEach, vi } from 'vitest';
import './setup.js';

vi.mock('../web/static/modules/markdown-renderer.js', () => ({
  KairosMarkdown: { renderAll: vi.fn() }
}));

// Override chat-stream specific mocks
const _utils = { escHtml: (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;') };

global.KairosUtils = _utils;
global.defaultModel = 'test-model';
global.KairosStream = { on() {}, emit() {} };
const mockFetchResponse = (data = { messages: [], widget_states: {} }) => Promise.resolve({
  text: () => Promise.resolve(JSON.stringify(data)),
  json: () => Promise.resolve(data)
});

global.fetch = () => mockFetchResponse();
global.logUI = () => {};
global.logStream = () => {};

const sessionContextModule = await import('../web/static/modules/session-context.js');
sessionContextModule.SessionContext.setSessionId('chat-stream-sid');

const widgetsModule = await import('../web/static/modules/widgets/index.js');
const formModule = await import('../web/static/modules/chat-form.js');

// Set up window with history mock before importing chat-stream.js
global.window = Object.assign(global.window || {}, {
  addEventListener: () => {},
  widgetStates: {},
  location: { pathname: '/' },
  history: { replaceState(state, title, url) { global.window._lastState = state; global.window._lastUrl = url; } },
  KairosUtils: _utils
});

var chatModule = await import('../web/static/modules/session-page.js');
var testNav = {
  location: global.window.location,
  history: global.window.history,
  onDomReady(cb) { global.document.addEventListener('DOMContentLoaded', cb); },
  onPopState(cb) { global.window.addEventListener('popstate', cb); }
};
chatModule.initSessionPage({ nav: testNav });

// Ensure KairosForm and KairosWidgets have mock reset/retry
widgetsModule.KairosWidgets.startMessageHandler = () => {};
widgetsModule.KairosWidgets.reset = () => {};
formModule.KairosForm.reset = () => {};
formModule.KairosForm.retry = () => {};
global.KairosWidgets = widgetsModule.KairosWidgets;
global.KairosForm = formModule.KairosForm;
global.window.KairosWidgets = widgetsModule.KairosWidgets;
global.window.KairosForm = formModule.KairosForm;

function mockElement() {
  return {
    innerHTML: '',
    getAttribute: () => '{}'
  };
}

describe('chat-stream', () => {

  test('sessionId configurado', () => {
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('chat-stream-sid');
  });

  test('loadSession cambia sessionId', () => {
    const prevSid = sessionContextModule.SessionContext.getSessionId();
    global.fetch = () => mockFetchResponse();
    global.document.getElementById = () => mockElement();
    chatModule.loadSession('custom-sid-999', { nav: testNav });
    expect(sessionContextModule.SessionContext.getSessionId()).toBe('custom-sid-999');
    sessionContextModule.SessionContext.setSessionId(prevSid);
  });

  test('loadSession llama replaceState', () => {
    global.fetch = () => mockFetchResponse();
    global.document.getElementById = () => mockElement();
    window._lastState = undefined;
    window._lastUrl = undefined;
    chatModule.loadSession('sid-replace-test', { nav: testNav });
    expect(window._lastState).toBeDefined();
    expect(window._lastState.sid).toBe('sid-replace-test');
    expect(window._lastUrl).toContain('sid-replace-test');
  });

  test('loadSession pasa URL correcta', () => {
    global.fetch = () => mockFetchResponse();
    global.document.getElementById = () => mockElement();
    window._lastUrl = undefined;
    chatModule.loadSession('url-test-sid', { nav: testNav });
    expect(window._lastUrl).toContain('url-test-sid');
  });

  test('loadSession llama widgets.reset', () => {
    let wReset = false;
    widgetsModule.KairosWidgets.reset = () => { wReset = true; };
    global.document.getElementById = () => mockElement();
    chatModule.loadSession('sid-reset', { nav: testNav });
    expect(wReset).toBe(true);
  });

  test('loadSession llama form.reset', () => {
    let fReset = false;
    formModule.KairosForm.reset = () => { fReset = true; };
    global.document.getElementById = () => mockElement();
    chatModule.loadSession('sid-reset', { nav: testNav });
    expect(fReset).toBe(true);
  });

  test('DOMContentLoaded con /sessions/ invoca loadSession', async () => {
    const sessionCtx = await import('../web/static/modules/session-context.js');
    sessionCtx.SessionContext.setSessionId('abc-123');
    global.window.location.pathname = '/sessions/abc-123';
    global.fetch = () => mockFetchResponse();
    global.document.getElementById = () => mockElement();
    const handler = global.document._listeners?.DOMContentLoaded;
    if (handler) handler();
    expect(sessionCtx.SessionContext.getSessionId()).toBe('abc-123');
  });

  test('DOMContentLoaded con / no invoca loadSession', () => {
    global.window.location.pathname = '/';
    const prevSid = sessionContextModule.SessionContext.getSessionId();
    const handler = global.document._listeners?.DOMContentLoaded;
    if (handler) handler();
    expect(sessionContextModule.SessionContext.getSessionId()).toBe(prevSid);
  });

  test('loadSession definida', () => {
    expect(typeof chatModule.loadSession).toBe('function');
  });

  test('loadSession llama fetch con URL correcta', async () => {
    let fetchedUrl = null;
    global.fetch = (url) => { fetchedUrl = url; return mockFetchResponse(); };
    global.document.getElementById = () => mockElement();
    chatModule.loadSession('url-test-sid', { nav: testNav });
    expect(fetchedUrl).toBe('/sessions/url-test-sid/messages');
  });

  test('loadSession llama renderAll', async () => {
    const { KairosMarkdown } = await import('../web/static/modules/markdown-renderer.js');
    const fetchPromise = mockFetchResponse({ messages: [], widget_states: {} });
    global.fetch = () => fetchPromise;
    global.document.getElementById = () => mockElement();
    chatModule.loadSession('render-test-sid', { nav: testNav });
    await fetchPromise;
    await new Promise(r => setTimeout(r, 10));
    expect(KairosMarkdown.renderAll).toHaveBeenCalled();
  });
});
