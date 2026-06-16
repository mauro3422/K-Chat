import { describe, it, expect } from 'vitest';
import { ErrorRenderer } from '../streaming/error-renderer';
import { C } from '../core/infra/DomContracts';
import { StreamHandlerContext } from '../streaming/ContentHandler';

describe('ErrorRenderer DOM contract', () => {
  function createContext(): StreamHandlerContext {
    const msgEl = document.createElement('div');
    msgEl.className = 'msg assistant live-msg';
    const bodyEl = document.createElement('div');
    bodyEl.className = C.MSG_BODY;
    msgEl.appendChild(bodyEl);
    return {
      msgEl,
      bodyEl,
      phaseIndex: 0,
      contentTexts: [''],
      reasoningTexts: [],
      firstToken: true,
      _renderedKeys: {},
    };
  }

  const ensureBody = (ctx: StreamHandlerContext) => ctx.bodyEl!;
  const escHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  it('creates an error-card in msg-body for general errors', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();

    const data = JSON.stringify({ type: 'server', message: 'Internal server error' });
    renderer.handleError(data, ctx);

    const card = ctx.bodyEl!.querySelector('.' + C.ERROR_CARD);
    expect(card).not.toBeNull();
    expect(card!.classList.contains(C.RATE_LIMIT_CARD)).toBe(false);
  });

  it('creates error-card with error-header and error-detail', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();

    renderer.handleError(JSON.stringify({ type: 'server', message: 'Something broke' }), ctx);

    const header = ctx.bodyEl!.querySelector('.' + C.ERROR_HEADER);
    expect(header).not.toBeNull();
    expect(header!.textContent).toContain('Respuesta interrumpida');

    const detail = ctx.bodyEl!.querySelector('.' + C.ERROR_DETAIL);
    expect(detail!.textContent).toContain('Something broke');
  });

  it('creates retry button on error-card', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();
    ctx.msgEl.dataset.userText = 'Hello';

    renderer.handleError(JSON.stringify({ type: 'server', message: 'Error' }), ctx);

    const retryBtn = ctx.bodyEl!.querySelector('.' + C.RETRY_BTN);
    expect(retryBtn).not.toBeNull();
    expect(retryBtn!.getAttribute('data-user-text')).toBe('Hello');
  });

  it('creates rate-limit-card for rate_limit errors', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();

    renderer.handleError(JSON.stringify({ type: 'rate_limit', message: 'Too many requests' }), ctx);

    const card = ctx.bodyEl!.querySelector('.' + C.ERROR_CARD);
    expect(card!.classList.contains(C.RATE_LIMIT_CARD)).toBe(true);
  });

  it('rate limit card has error-hint', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();

    renderer.handleError(JSON.stringify({ type: 'rate_limit', message: 'Limit' }), ctx);

    const hint = ctx.bodyEl!.querySelector('.' + C.ERROR_HINT);
    expect(hint).not.toBeNull();
    expect(hint!.textContent).toContain('Límite del proveedor');
  });

  it('rate limit card does NOT have retry button', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();

    renderer.handleError(JSON.stringify({ type: 'rate_limit', message: 'Limit' }), ctx);

    const retryBtn = ctx.bodyEl!.querySelector('.' + C.RETRY_BTN);
    expect(retryBtn).toBeNull();
  });

  it('clears placeholder before inserting error', () => {
    const renderer = new ErrorRenderer(ensureBody, escHtml);
    const ctx = createContext();
    ctx.bodyEl!.textContent = '✍️ Escribiendo...';

    renderer.handleError(JSON.stringify({ type: 'network', message: 'Failed' }), ctx);

    const card = ctx.bodyEl!.querySelector('.' + C.ERROR_CARD);
    expect(card).not.toBeNull();
    expect(ctx.bodyEl!.children.length).toBe(1);
  });
});
