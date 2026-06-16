import { describe, it, expect, beforeEach } from 'vitest';
import { ToolCallRenderer } from '../streaming/tool-call-renderer';
import { C } from '../core/infra/DomContracts';
import { StreamHandlerContext } from '../streaming/ContentHandler';

describe('ToolCallRenderer DOM contract', () => {
  let insertBeforeBody: (ctx: StreamHandlerContext, el: HTMLElement) => void;
  const autoScroll = () => {};

  function createContext(phaseIndex = 0): StreamHandlerContext {
    const msgEl = document.createElement('div');
    msgEl.className = 'msg assistant live-msg';
    const bodyEl = document.createElement('div');
    bodyEl.className = C.MSG_BODY;
    msgEl.appendChild(bodyEl);
    return {
      msgEl,
      bodyEl,
      phaseIndex,
      contentTexts: [''],
      reasoningTexts: [],
      firstToken: true,
      _renderedKeys: {},
    };
  }

  beforeEach(() => {
    insertBeforeBody = (ctx, el) => {
      const body = ctx.bodyEl;
      if (body && body.parentNode) {
        body.parentNode.insertBefore(el, body);
      }
    };
  });

  it('creates a tool-calls wrapper with dataset.phase', () => {
    const renderer = new ToolCallRenderer(insertBeforeBody, autoScroll);
    const ctx = createContext(0);

    renderer.handleToolCall(JSON.stringify({ name: 'search', status: 'calling' }), ctx);

    const wrapper = ctx.msgEl.querySelector('.' + C.TOOL_CALLS) as HTMLElement;
    expect(wrapper).not.toBeNull();
    expect(wrapper.dataset.phase).toBe('0');
  });

  it('creates calling pill with tc-spinner', () => {
    const renderer = new ToolCallRenderer(insertBeforeBody, autoScroll);
    const ctx = createContext(0);

    renderer.handleToolCall(JSON.stringify({ name: 'search_web', status: 'calling' }), ctx);

    const pill = ctx.msgEl.querySelector('.' + C.TC_ITEM_CALLING.replace(' ', '.'));
    expect(pill).not.toBeNull();
    expect(pill!.dataset.tool).toBe('search_web');
    expect(pill!.querySelector('.tc-spinner')).not.toBeNull();
  });

  it('transitions from calling to ok', () => {
    const renderer = new ToolCallRenderer(insertBeforeBody, autoScroll);
    const ctx = createContext(0);

    renderer.handleToolCall(JSON.stringify({ name: 'search', status: 'calling' }), ctx);
    renderer.handleToolCall(JSON.stringify({ name: 'search', status: 'ok' }), ctx);

    const pill = ctx.msgEl.querySelector('[data-tool="search"]');
    expect(pill).not.toBeNull();
    expect(pill!.className).toContain('ok');
    expect(pill!.textContent).toContain('✓');
  });

  it('transitions from calling to error', () => {
    const renderer = new ToolCallRenderer(insertBeforeBody, autoScroll);
    const ctx = createContext(0);

    renderer.handleToolCall(JSON.stringify({ name: 'web_search', status: 'calling' }), ctx);
    renderer.handleToolCall(JSON.stringify({ name: 'web_search', status: 'error' }), ctx);

    const pill = ctx.msgEl.querySelector('[data-tool="web_search"]');
    expect(pill!.className).toContain('error');
    expect(pill!.textContent).toContain('✗');
  });

  it('increments phaseIndex when tool completes', () => {
    const renderer = new ToolCallRenderer(insertBeforeBody, autoScroll);
    const ctx = createContext(0);

    expect(ctx.phaseIndex).toBe(0);
    renderer.handleToolCall(JSON.stringify({ name: 'search', status: 'calling' }), ctx);
    expect(ctx.phaseIndex).toBe(0);

    renderer.handleToolCall(JSON.stringify({ name: 'search', status: 'ok' }), ctx);
    expect(ctx.phaseIndex).toBe(1);
  });

  it('inserts tool-calls before msg-body', () => {
    const renderer = new ToolCallRenderer(insertBeforeBody, autoScroll);
    const ctx = createContext(0);

    renderer.handleToolCall(JSON.stringify({ name: 'search', status: 'calling' }), ctx);

    const msgChildren = Array.from(ctx.msgEl.children);
    const bodyIndex = msgChildren.indexOf(ctx.bodyEl!);
    const tcIndex = msgChildren.indexOf(ctx.msgEl.querySelector('.' + C.TOOL_CALLS)!);
    expect(tcIndex).toBeLessThan(bodyIndex);
  });
});
