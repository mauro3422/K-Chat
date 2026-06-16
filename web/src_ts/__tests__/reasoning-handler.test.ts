import { describe, it, expect } from 'vitest';
import { ReasoningHandler } from '../streaming/reasoning-handler';
import { C } from '../core/infra/DomContracts';
import { StreamHandlerContext } from '../streaming/ContentHandler';

describe('ReasoningHandler DOM contract', () => {
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

  const insertBeforeBody = (ctx: StreamHandlerContext, el: HTMLElement) => {
    const body = ctx.bodyEl;
    if (body && body.parentNode) {
      body.parentNode.insertBefore(el, body);
    }
  };

  const autoScroll = () => {};

  describe('handleReasoning()', () => {
    it('creates a details.reasoning element', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleReasoning('First reasoning step', ctx);

      const details = ctx.msgEl.querySelector('details.' + C.REASONING);
      expect(details).not.toBeNull();
      expect(details!.getAttribute('open')).toBe('');
    });

    it('has summary text "Razonando..." for first phase', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleReasoning('thinking', ctx);

      const summary = ctx.msgEl.querySelector('details.' + C.REASONING + ' summary');
      expect(summary).not.toBeNull();
      expect(summary!.textContent).toBe('Razonando...');
    });

    it('has summary with phase number for subsequent phases', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(1);
      handler.handleReasoning('more thinking', ctx);

      const summary = ctx.msgEl.querySelector('details.' + C.REASONING + ' summary');
      expect(summary!.textContent).toContain('Fase 2');
    });

    it('has dataset.phase set correctly', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleReasoning('data', ctx);

      const details = ctx.msgEl.querySelector('details.' + C.REASONING) as HTMLElement;
      expect(details.dataset.phase).toBe('0');
    });

    it('accumulates text content across calls', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleReasoning('Step 1. ', ctx);
      handler.handleReasoning('Step 2.', ctx);

      const rt = ctx.msgEl.querySelector('details.' + C.REASONING + ' .' + C.RT);
      expect(rt!.textContent).toBe('Step 1. Step 2.');
    });

    it('inserts reasoning BEFORE msg-body', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleReasoning('thinking', ctx);

      const msgChildren = Array.from(ctx.msgEl.children);
      const bodyIndex = msgChildren.indexOf(ctx.bodyEl!);
      const detailsIndex = msgChildren.indexOf(ctx.msgEl.querySelector('details.' + C.REASONING)!);
      expect(detailsIndex).toBeLessThan(bodyIndex);
    });

    it('appends reasoning text to reasoningTexts', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleReasoning('text1', ctx);
      handler.handleReasoning('text2', ctx);
      expect(ctx.reasoningTexts[0]).toBe('text1text2');
    });
  });

  describe('handleMemory()', () => {
    it('creates a details with reasoning memories-phase classes', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleMemory('Some memory', ctx);

      const details = ctx.msgEl.querySelector('details.' + C.REASONING_MEMORIES.replace(' ', '.'));
      expect(details).not.toBeNull();
    });

    it('has summary with Memorias', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleMemory('mem', ctx);

      const summary = ctx.msgEl.querySelector('details.' + C.REASONING_MEMORIES.replace(' ', '.') + ' summary');
      expect(summary!.textContent).toBe('📖 Memorias');
    });

    it('has content div with rt memory-content classes', () => {
      const handler = new ReasoningHandler(insertBeforeBody, autoScroll);
      const ctx = createContext(0);
      handler.handleMemory('memory content', ctx);

      const contentDiv = ctx.msgEl.querySelector('details.' + C.REASONING_MEMORIES.replace(' ', '.') + ' .' + C.MEMORY_CONTENT.replace(' ', '.'));
      expect(contentDiv).not.toBeNull();
      expect(contentDiv!.textContent).toBe('memory content');
    });
  });
});
