import { describe, test, expect, vi } from 'vitest';
import './setup.js';

const { handler } = vi.hoisted(() => ({ handler: vi.fn() }));
vi.mock('../web/static/modules/stream-error-handler.js', () => ({
  StreamErrorHandler: {
    handler,
  },
}));

const { executeStreamFetch } = await import('../web/static/modules/stream-fetcher.js');

describe('executeStreamFetch', () => {
  test('silencia AbortError sin tratarlo como error de red', async () => {
    const abortErr = new Error('signal is aborted without reason');
    abortErr.name = 'AbortError';
    global.fetch = vi.fn(() => Promise.reject(abortErr));
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    await expect(executeStreamFetch({
      sessionId: 'sid-1',
      defaultModel: 'model-1',
      text: 'hola',
      controller: new AbortController(),
      errorHandler: { handler: vi.fn() },
      context: { isFirstToken: () => false, clearFirstToken: () => {}, getBodyDivs: () => [] },
    })).rejects.toMatchObject({ name: 'AbortError' });

    expect(consoleSpy).not.toHaveBeenCalled();
    expect(handler).not.toHaveBeenCalled();

    consoleSpy.mockRestore();
  });
});
