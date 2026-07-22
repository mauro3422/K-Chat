import { describe, expect, it, vi } from 'vitest';
import { NDJSONStreamClient } from '../streaming/NDJSONStreamClient';

describe('NDJSONStreamClient heartbeat', () => {
  it('reports heartbeat activity without dispatching it as visible content', async () => {
    const body = [
      JSON.stringify({ t: 'heartbeat', d: '' }),
      JSON.stringify({ t: 'content', d: 'terminado' }),
      '',
    ].join('\n');
    const apiClient = {
      chatStream: vi.fn(async () => new Response(body, { status: 200 })),
    };
    const dispatcher = { emit: vi.fn() };
    const onChunk = vi.fn();

    const client = new NDJSONStreamClient(apiClient as any);
    await client.startStream({
      sessionId: 's1',
      message: 'crear documento',
      dispatcher: dispatcher as any,
      context: {},
      onChunk,
    });

    expect(onChunk).toHaveBeenCalledOnce();
    expect(dispatcher.emit).toHaveBeenCalledOnce();
    expect(dispatcher.emit).toHaveBeenCalledWith('content', 'terminado', {});
  });
});
