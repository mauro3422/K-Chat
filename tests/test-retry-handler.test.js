import { describe, test, expect } from 'vitest';
import './setup.js';

const retryModulePath = new URL('../web/static/modules/retry-handler.js', import.meta.url).pathname;

describe('RetryController', () => {
  test('controllers do not share retry count', async () => {
    const mod = await import(`file://${retryModulePath}?t=${Date.now()}`);
    const a = mod.createRetryController();
    const b = mod.createRetryController();

    a.incrementRetry();
    a.incrementRetry();

    expect(a.getRetryCount()).toBe(2);
    expect(b.getRetryCount()).toBe(0);
    b.incrementRetry();
    expect(a.getRetryCount()).toBe(2);
    expect(b.getRetryCount()).toBe(1);
  });

  test('stream timeout is per controller instance', async () => {
    const mod = await import(`file://${retryModulePath}?t=${Date.now()}`);
    const a = mod.createRetryController();
    const b = mod.createRetryController();

    a.streamTimeout = 5000;
    expect(a.getStreamTimeout()).toBe(5000);
    expect(b.getStreamTimeout()).toBe(120000);
  });
});

