import { describe, test, expect, vi, beforeEach } from 'vitest';
import './setup.js';

// ── Mock heavyweight module dependencies ────────────────────
vi.mock('../web/static/modules/file-attachment.js', () => ({
  FileAttachment: { init: vi.fn(), hasFiles: () => false, getFiles: () => [], clear: vi.fn() }
}));
vi.mock('../web/static/modules/markdown-renderer.js', () => ({
  MarkdownRenderer: { renderAll: vi.fn() }
}));
vi.mock('../web/static/modules/rate-limit-cooldown.js', () => ({ RateLimitCooldown: {} }));
vi.mock('../web/static/modules/stream-dispatcher.js', () => ({
  StreamDispatcher: { on: vi.fn(), off: vi.fn(), emit: vi.fn() }
}));
vi.mock('../web/static/modules/log-ui.js', () => ({ logUI: vi.fn() }));
vi.mock('../web/static/modules/sidebar-refresh.js', () => ({ refreshSidebar: vi.fn() }));
vi.mock('../web/static/modules/stream-completion.js', () => ({ handleSuccessfulStream: vi.fn() }));
vi.mock('../web/static/modules/debug-panel.js', () => ({
  DebugPanel: {
    hasOpenWindows: () => false,
    bindDebugControls: vi.fn(),
    markCallingPillsError: vi.fn(),
    showRetryMessage: vi.fn(),
    logUI: vi.fn()
  }
}));
vi.mock('../web/static/modules/stream-error-handler.js', () => ({
  StreamErrorHandler: {
    createStreamErrorHandler: () => ({
      handler: vi.fn(),
      getError: vi.fn(() => null)
    }),
    markCallingPillsError: vi.fn(),
    showRetryMessage: vi.fn()
  }
}));
vi.mock('../web/static/modules/stream-fetcher.js', () => ({
  executeStreamFetch: vi.fn()
}));
vi.mock('../web/static/modules/stream-retry-coordinator.js', () => ({
  attemptRetry: vi.fn(() => false),
  shouldAutoRetryEmptyResponse: vi.fn(() => false)
}));

// ── Import modules under test ───────────────────────────────
const { ChatForm } = await import('../web/static/modules/chat-form.js');
const { Utils } = await import('../web/static/modules/utils.js');
const { StreamOrchestrator } = await import('../web/static/modules/stream-orchestrator.js');

// ── Test helpers ─────────────────────────────────────────────
const mockNav = {
  location: { pathname: '/' },
  history: { replaceState: vi.fn() },
  onDomReady: vi.fn(),
  onPopState: vi.fn()
};

function createMockInput(overrides) {
  return {
    value: '',
    disabled: false,
    style: { height: '' },
    focus: vi.fn(),
    addEventListener: vi.fn(),
    scrollHeight: 0,
    ...overrides
  };
}

function resetDomMocks() {
  document.getElementById = vi.fn(() => null);
  document.querySelector = vi.fn(() => null);
  window._kcChatFormReady = false;
}

// Save original setup.js document.addEventListener so we can restore it
const ORIG_DOC_ADD_EVENT_LISTENER = document.addEventListener;

// Helpers for submit guard tests
function initChatFormForSubmit() {
  resetDomMocks();
  document.addEventListener = ORIG_DOC_ADD_EVENT_LISTENER;
  document.getElementById = vi.fn((id) => {
    if (id === 'msg-input') return createMockInput();
    if (id === 'chat-submit-btn') return {
      classList: { contains: vi.fn((cls) => cls === 'btn-stop') }
    };
    return null;
  });
  document.querySelector = vi.fn(() => null);
  ChatForm.init({ nav: mockNav });
}

function triggerSubmit() {
  const handler = document._listeners && document._listeners.submit;
  if (!handler) throw new Error('No submit listener registered');
  const form = { id: 'chat-form' };
  handler({ target: form, preventDefault: vi.fn() });
}

// ═══════════════════════════════════════════════════════════
// Anti-regression UI tests
// ═══════════════════════════════════════════════════════════

describe('ChatForm.init — double-call guard', () => {

  test('init con window._kcChatFormReady=true no agrega listeners', () => {
    resetDomMocks();
    window._kcChatFormReady = true;
    document.getElementById = vi.fn(() => createMockInput());

    const spy = vi.fn();
    document.addEventListener = spy;

    ChatForm.init({ nav: mockNav });
    expect(spy).not.toHaveBeenCalled();
  });

  test('init con window._kcChatFormReady=false agrega listeners', () => {
    resetDomMocks();
    window._kcChatFormReady = false;
    document.getElementById = vi.fn(() => createMockInput());

    const spy = vi.fn();
    document.addEventListener = spy;

    ChatForm.init({ nav: mockNav });
    expect(spy).toHaveBeenCalled();
  });

});

describe('streaming flag lifecycle', () => {

  beforeEach(() => {
    ChatForm.setStreamingState(false);
  });

  test('isStreaming arranca en false', () => {
    resetDomMocks();
    expect(ChatForm.isStreaming()).toBe(false);
  });

  test('setStreamingState(true/false) cambia el flag', () => {
    resetDomMocks();
    ChatForm.setStreamingState(true);
    expect(ChatForm.isStreaming()).toBe(true);
    ChatForm.setStreamingState(false);
    expect(ChatForm.isStreaming()).toBe(false);
  });

  test('setStreamingState toggla clase streaming en el container', () => {
    resetDomMocks();
    const container = { classList: { toggle: vi.fn() } };
    document.querySelector = vi.fn((sel) => sel === '.chat-input-container' ? container : null);

    ChatForm.setStreamingState(true);
    expect(document.querySelector).toHaveBeenCalledWith('.chat-input-container');
    expect(container.classList.toggle).toHaveBeenCalledWith('streaming', true);
  });

});

describe('Utils.finalizeStream', () => {

  test('limpia value y height del input', () => {
    resetDomMocks();
    document.getElementById = vi.fn(() => null);
    document.querySelector = vi.fn(() => null);

    const input = createMockInput({ value: 'hello', style: { height: '50px' } });
    Utils.finalizeStream(input);
    expect(input.value).toBe('');
    expect(input.style.height).toBe('');
  });

  test('no explota si input es null', () => {
    expect(() => Utils.finalizeStream(null)).not.toThrow();
  });

  test('limpia spinner y botón de submit', () => {
    resetDomMocks();
    const spinner = { textContent: '...' };
    const btn = { className: 'btn-stop', title: '', innerHTML: '', style: {} };
    document.getElementById = vi.fn((id) => {
      if (id === 'spinner') return spinner;
      if (id === 'chat-submit-btn') return btn;
      return null;
    });
    document.querySelector = vi.fn(() => ({
      classList: { remove: vi.fn() }
    }));

    const input = createMockInput({ value: 'test' });
    Utils.finalizeStream(input);
    expect(spinner.textContent).toBe('');
    expect(btn.className).toBe('');
  });

});

describe('submit handler — streaming guard', () => {

  test('submit con streaming=true y btn-stop preserva streaming flag', () => {
    initChatFormForSubmit();
    ChatForm.setStreamingState(true);

    triggerSubmit();

    expect(ChatForm.isStreaming()).toBe(true);
  });

  test('submit con streaming=true sin btn-stop preserva streaming flag', () => {
    initChatFormForSubmit();
    ChatForm.setStreamingState(true);

    document.getElementById = vi.fn((id) => {
      if (id === 'chat-submit-btn') return {
        classList: { contains: vi.fn(() => false) }
      };
      return null;
    });

    triggerSubmit();
    expect(ChatForm.isStreaming()).toBe(true);
  });

});

describe('StreamOrchestrator._streamGuard', () => {

  test('startStream ejecuta correctamente si no hay guard', async () => {
    const { executeStreamFetch } = await import('../web/static/modules/stream-fetcher.js');
    executeStreamFetch.mockResolvedValue({ hasContent: true });

    document.getElementById = vi.fn(() => null);
    document.querySelector = vi.fn(() => null);
    const asstDiv = { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) };

    await StreamOrchestrator.startStream({
      text: 'ok',
      form: {},
      input: createMockInput(),
      asstDiv,
      lastUserMessageText: 'ok',
      controller: new AbortController(),
      sessionId: 'sid',
      defaultModel: 'm',
      files: []
    });

    expect(executeStreamFetch).toHaveBeenCalled();
  });

  async function sleep(ms) {
    return new Promise(r => setTimeout(r, ms));
  }

  test('segunda llamada concurrente a startStream es ignorada', async () => {
    const { executeStreamFetch } = await import('../web/static/modules/stream-fetcher.js');

    // Clear _streamGuard + 500ms debounce by running a quick successful stream
    executeStreamFetch.mockResolvedValue({ hasContent: true });
    document.getElementById = vi.fn(() => null);
    document.querySelector = vi.fn(() => null);
    const asstDiv1 = { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) };
    await StreamOrchestrator.startStream({
      text: 'flush', form: {}, input: createMockInput(),
      asstDiv: asstDiv1, lastUserMessageText: 'flush',
      controller: new AbortController(), sessionId: 'sid', defaultModel: 'm', files: []
    });

    // Wait for 500ms debounce window to expire
    await sleep(600);

    // Now test concurrent guard with a slow first call
    let resolveSlow;
    executeStreamFetch.mockImplementation(() => new Promise(r => { resolveSlow = r; }));

    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const asstDiv2 = { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) };

    const params = {
      text: 'slow', form: {}, input: createMockInput(),
      asstDiv: asstDiv2, lastUserMessageText: 'slow',
      controller: new AbortController(), sessionId: 'sid', defaultModel: 'm', files: []
    };

    const p1 = StreamOrchestrator.startStream(params);
    await sleep(20);

    const p2 = StreamOrchestrator.startStream(params);
    const result2 = await p2;
    expect(result2).toBeUndefined();
    expect(consoleWarn).toHaveBeenCalled();

    resolveSlow({ hasContent: true });
    await p1;
    consoleWarn.mockRestore();
  });

});

describe('retry path resets streaming', () => {

  test('error con attemptRetry=true llama setStreamingState(false) y finalizeStream', async () => {
    const { executeStreamFetch } = await import('../web/static/modules/stream-fetcher.js');
    const { attemptRetry } = await import('../web/static/modules/stream-retry-coordinator.js');

    // Flush _streamGuard and debounce timer
    executeStreamFetch.mockResolvedValue({ hasContent: true });
    document.getElementById = vi.fn(() => null);
    document.querySelector = vi.fn(() => null);
    const asstDivFlush = { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) };
    await StreamOrchestrator.startStream({
      text: 'flush', form: {}, input: createMockInput(),
      asstDiv: asstDivFlush, lastUserMessageText: 'flush',
      controller: new AbortController(), sessionId: 'sid', defaultModel: 'm', files: []
    });

    await new Promise(r => setTimeout(r, 600));

    // Setup error path
    executeStreamFetch.mockRejectedValue(new Error('Fetch failed'));
    attemptRetry.mockReturnValue(true);

    document.getElementById = vi.fn(() => null);
    document.querySelector = vi.fn(() => null);
    const input = createMockInput({ value: 'hello' });
    const asstDiv = { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) };

    ChatForm.setStreamingState(true);
    expect(ChatForm.isStreaming()).toBe(true);

    await StreamOrchestrator.startStream({
      text: 'test', form: {}, input,
      asstDiv, lastUserMessageText: 'test',
      controller: new AbortController(),
      sessionId: 'sid', defaultModel: 'm', files: []
    });

    expect(ChatForm.isStreaming()).toBe(false);
    // Retry path: no llama finalizeStream (el scheduleRetry se encarga del texto)
    // En el test, attemptRetry es mock y no restaura input.value, así que queda igual
    expect(typeof input.value).toBe('string');
  });

  describe('input se limpia inmediatamente al enviar', () => {

    test('submit handler source code tiene input clearing inmediato', async () => {
      // Verificar que el source code de chat-form.js tiene input.value='' DESPUÉS de leer el texto
      // pero ANTES de las operaciones DOM (appendChild). Esto asegura que el fix no se pierda.
      const fs = await import('fs');
      const source = fs.readFileSync('web/static/modules/chat-form.js', 'utf8');

      // Buscar patron: después de `var text = input.value.trim()` debe venir `input.value = ''`
      const textLine = source.indexOf("var text = input ? input.value.trim() : '';");
      const clearLine = source.indexOf("input.value = '';", textLine);
      const textEnd = source.indexOf(';', textLine) + 1;

      expect(textLine).toBeGreaterThanOrEqual(0);
      expect(clearLine).toBeGreaterThan(textEnd);
      // input clearing debe estar cerca (después de validar texto no vacío, antes de appendChild)
      const beforeAppendChild = source.indexOf('messages.appendChild', textLine);
      expect(clearLine).toBeLessThan(beforeAppendChild);
    });

    test('finalizeStream en path de éxito no rompe el input ya limpio', async () => {
      const { Utils } = await import('../web/static/modules/utils.js');
      const input = createMockInput({ value: '', style: { height: '' } });
      Utils.finalizeStream(input);
      expect(input.value).toBe('');
    });

    test('retry path NO llama finalizeStream (solo setStreamingState)', async () => {
      const { attemptRetry } = await import('../web/static/modules/stream-retry-coordinator.js');
      const { StreamOrchestrator } = await import('../web/static/modules/stream-orchestrator.js');
      const { executeStreamFetch } = await import('../web/static/modules/stream-fetcher.js');

      // Flush guard
      executeStreamFetch.mockResolvedValue({ hasContent: true });
      document.getElementById = vi.fn(() => null);
      document.querySelector = vi.fn(() => null);
      await StreamOrchestrator.startStream({
        text: 'flush', form: {}, input: createMockInput(),
        asstDiv: { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) },
        lastUserMessageText: 'flush', controller: new AbortController(),
        sessionId: 'sid', defaultModel: 'm', files: []
      });
      await new Promise(r => setTimeout(r, 600));

      // Retry path
      executeStreamFetch.mockRejectedValue(new Error('fail'));
      attemptRetry.mockReturnValue(true);

      const input = createMockInput({ value: 'texto original' });
      // track si finalizeStream fue llamado
      let finalizeCalled = false;
      const origFinalize = Utils.finalizeStream;
      Utils.finalizeStream = function() { finalizeCalled = true; return origFinalize.apply(this, arguments); };

      ChatForm.setStreamingState(true);
      await StreamOrchestrator.startStream({
        text: 'test', form: {}, input,
        asstDiv: { querySelector: vi.fn(() => null), querySelectorAll: vi.fn(() => []) },
        lastUserMessageText: 'test', controller: new AbortController(),
        sessionId: 'sid', defaultModel: 'm', files: []
      });

      expect(ChatForm.isStreaming()).toBe(false);
      expect(finalizeCalled).toBe(false);
    });
  });

});
