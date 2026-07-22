import { afterEach, describe, expect, it, vi } from 'vitest';

import { ApiClient } from '../api/ApiClient';

describe('ApiClient browser diagnostics', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses the browser-safe diagnostics facade for LAN status', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));
    const client = new ApiClient();

    await client.syncStatus();

    expect(fetchSpy).toHaveBeenCalledWith('/api/diagnostics', { cache: 'no-store' });
  });

  it('uses the browser-safe diagnostics facade for memory status', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}'));
    const client = new ApiClient();

    await client.memoryDiagnostics('user:*');

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/diagnostics?key_pattern=user%3A*',
      { cache: 'no-store' },
    );
  });
});
