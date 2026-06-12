import { describe, test, expect } from 'vitest';
import './setup.js';

const mod = await import('../web/static/modules/stream-retry-coordinator.js');

describe('stream-retry-coordinator', () => {
  test('does not auto retry empty response after reasoning', () => {
    expect(mod.shouldAutoRetryEmptyResponse({
      hasContent: false,
      hadReasoning: true,
      hadToolCalls: false
    })).toBe(false);
  });

  test('does not auto retry empty response after tool calls', () => {
    expect(mod.shouldAutoRetryEmptyResponse({
      hasContent: false,
      hadReasoning: false,
      hadToolCalls: true
    })).toBe(false);
  });

  test('can auto retry empty response without activity', () => {
    expect(mod.shouldAutoRetryEmptyResponse({
      hasContent: false,
      hadReasoning: false,
      hadToolCalls: false
    })).toBe(true);
  });
});
