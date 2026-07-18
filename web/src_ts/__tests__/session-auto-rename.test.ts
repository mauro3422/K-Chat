import { describe, expect, it, vi } from 'vitest';

import { TypedEventBus } from '../core/infra/EventBus';
import { SessionStore } from '../core/session/SessionStore';
import { SSEClient } from '../streaming/SSEClient';

describe('session auto-rename propagation', () => {
  it('forwards the server event through the client event bus', () => {
    const eventBus = { emit: vi.fn() };
    const client = new SSEClient(
      eventBus as never,
      {} as never,
      {} as never,
      {} as never,
      {} as never,
      (markdown: string) => markdown,
    );

    (client as unknown as { handleMessage(event: MessageEvent): void }).handleMessage({
      data: JSON.stringify({
        type: 'session_renamed',
        data: { session_id: 'session-1', name: 'Título inteligente' },
      }),
    } as MessageEvent);

    expect(eventBus.emit).toHaveBeenCalledWith('sse:session-renamed', {
      id: 'session-1',
      name: 'Título inteligente',
    });
  });

  it('updates the stored session name without another rename request', async () => {
    const apiClient = {
      getSessions: vi.fn(async () => new Response(JSON.stringify([{
        id: 'session-1',
        name: '',
        count: 1,
        last_str: '2026-07-18',
      }]))),
      getSessionMessages: vi.fn(async () => new Response(JSON.stringify({ messages: [] }))),
      renameSession: vi.fn(),
    };
    const eventBus = new TypedEventBus();
    const store = new SessionStore(apiClient as never);
    await store.init(eventBus, 'session-1');

    eventBus.emit('sse:session-renamed', {
      id: 'session-1',
      name: 'Título inteligente',
    });

    expect(store.sessions[0].name).toBe('Título inteligente');
    expect(apiClient.renameSession).not.toHaveBeenCalled();
  });
});
