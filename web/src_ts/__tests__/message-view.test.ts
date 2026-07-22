import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { MessageView } from '../rendering/MessageView';
import { C } from '../core/infra/DomContracts';
const renderer = {
  renderMessage: (container: HTMLElement, content: string, isMarkdown: boolean) => {
    container.innerHTML = isMarkdown ? content : content;
  },
  renderReasoning: () => {},
  renderToolCall: () => {},
  clearThinking: () => {},
};

describe('MessageView DOM contract', () => {
  let messageView: MessageView;
  let container: HTMLElement;

  beforeEach(() => {
    document.getElementById('messages')?.remove();
    container = document.createElement('div');
    container.id = 'messages';
    document.body.appendChild(container);

    messageView = new MessageView(renderer, undefined, undefined);
    messageView.init();
  });

  afterEach(() => {
    container.remove();
  });

  describe('beginStreaming()', () => {
    it('creates a live assistant message element', () => {
      const el = messageView.beginStreaming('assistant');
      expect(el).not.toBeNull();
      expect(el!.classList.contains('msg')).toBe(true);
      expect(el!.classList.contains('assistant')).toBe(true);
      expect(el!.classList.contains(C.LIVE_MSG)).toBe(true);
    });

    it('has msg-label with text "Kairos" for assistant', () => {
      const el = messageView.beginStreaming('assistant');
      const label = el!.querySelector('.' + C.MSG_LABEL);
      expect(label).not.toBeNull();
      expect(label!.textContent).toBe('Kairos');
    });

    it('has msg-body placeholder for assistant', () => {
      const el = messageView.beginStreaming('assistant');
      const body = el!.querySelector('.' + C.MSG_BODY);
      expect(body).not.toBeNull();
      expect(body!.textContent).toMatch(/Pensando/);
    });

    it('creates a user live message without body', () => {
      const el = messageView.beginStreaming('user');
      expect(el!.classList.contains('user')).toBe(true);
      const body = el!.querySelector('.' + C.MSG_BODY);
      expect(body).toBeNull();
    });

    it('appends message to the container', () => {
      const el = messageView.beginStreaming('assistant');
      expect(container.children.length).toBe(1);
      expect(container.children[0]).toBe(el);
    });

    it('removes empty state if present', () => {
      const emptyState = document.createElement('div');
      emptyState.className = C.EMPTY_STATE;
      container.appendChild(emptyState);
      expect(container.children.length).toBe(1);

      messageView.beginStreaming('assistant');
      expect(container.querySelector('.' + C.EMPTY_STATE)).toBeNull();
    });
  });

  describe('appendMessage() — simple', () => {
    it('creates a user message element', () => {
      const el = messageView.appendMessage({ role: 'user', content: 'Hello', ts: Date.now() });
      expect(el).not.toBeNull();
      expect(el!.classList.contains('user')).toBe(true);
      expect(el!.classList.contains('msg')).toBe(true);
    });

    it('creates an assistant message element', () => {
      const el = messageView.appendMessage({ role: 'assistant', content: 'Hi there', ts: Date.now() });
      expect(el!.classList.contains('assistant')).toBe(true);
      const body = el!.querySelector('.' + C.MSG_BODY);
      expect(body).not.toBeNull();
    });

    it('has msg-label with role-appropriate text', () => {
      const el = messageView.appendMessage({ role: 'user', content: 'Hello', ts: Date.now() });
      const label = el!.querySelector('.' + C.MSG_LABEL);
      expect(label!.textContent).toBe('Tu');
    });

    it('adds reasoning block for assistant messages', () => {
      const el = messageView.appendMessage({
        role: 'assistant',
        content: 'Answer',
        reasoning: 'Thinking step by step',
        ts: Date.now(),
      });
      const details = el!.querySelector('details.' + C.REASONING);
      expect(details).not.toBeNull();
      const rt = details!.querySelector('.' + C.RT);
      expect(rt).not.toBeNull();
      expect(rt!.textContent).toBe('Thinking step by step');
    });

    it('adds tool call pills when matched_tools provided', () => {
      const el = messageView.appendMessage({
        role: 'assistant',
        content: 'Done',
        ts: Date.now(),
        matched_tools: [{ tool_name: 'search_web', status: 'ok', turn: 1 }],
      });
      const tcWrapper = el!.querySelector('.' + C.TOOL_CALLS);
      expect(tcWrapper).not.toBeNull();
      const pill = tcWrapper!.querySelector('.' + C.TC_ITEM);
      expect(pill).not.toBeNull();
      expect(pill!.textContent).toContain('search_web');
    });

    it('sets dataset.ts and dataset.id', () => {
      const el = messageView.appendMessage({
        id: 42,
        role: 'user',
        content: 'test',
        ts: '2026-06-16T12:00:00Z',
      });
      expect(el!.dataset.id).toBe('42');
      expect(el!.dataset.ts).toBe('2026-06-16T12:00:00Z');
    });

    it('appends to container', () => {
      messageView.appendMessage({ role: 'user', content: 'A' });
      messageView.appendMessage({ role: 'assistant', content: 'B', ts: Date.now() });
      expect(container.children.length).toBe(2);
    });

    it('does not add msg-ts when ts is undefined', () => {
      const el = messageView.appendMessage({ role: 'user', content: 'test' });
      const ts = el!.querySelector('.' + C.MSG_TS);
      expect(ts).toBeNull();
    });

    it('restores retry checkpoint cards from persisted phases', () => {
      const el = messageView.appendMessage({
        role: 'assistant',
        content: 'terminado',
        phases: [
          { content: 'fase previa' },
          {
            retry: {
              attempt: 1,
              max_retries: 2,
              error_type: 'network',
              error_message: 'provider desconectado',
              status: 'completed',
            },
          },
          { content: 'fase recuperada' },
        ],
      });

      const card = el!.querySelector('.retry-checkpoint--completed');
      expect(card?.textContent).toContain('Intento 1/2');
      expect(card?.textContent).toContain('provider desconectado');
    });
  });

  describe('clearContainer()', () => {
    it('clears all messages', () => {
      messageView.appendMessage({ role: 'user', content: 'A' });
      messageView.appendMessage({ role: 'assistant', content: 'B', ts: Date.now() });
      expect(container.children.length).toBe(2);

      messageView.clearContainer();
      expect(container.children.length).toBe(0);
    });
  });
});
