import { describe, it, expect, vi } from 'vitest';
import { StreamDispatcher } from '../streaming/StreamDispatcher';

describe('StreamDispatcher event contract', () => {
  it('dispatches events to registered handlers', () => {
    const dispatcher = new StreamDispatcher<string>();
    const handler = vi.fn();

    dispatcher.on('content', handler);
    dispatcher.emit('content', 'hello', 'ctx');

    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith('hello', 'ctx');
  });

  it('supports multiple handlers for same event', () => {
    const dispatcher = new StreamDispatcher<number>();
    const h1 = vi.fn();
    const h2 = vi.fn();

    dispatcher.on('reasoning', h1);
    dispatcher.on('reasoning', h2);
    dispatcher.emit('reasoning', 'data', 42);

    expect(h1).toHaveBeenCalledWith('data', 42);
    expect(h2).toHaveBeenCalledWith('data', 42);
  });

  it('can remove a handler with off()', () => {
    const dispatcher = new StreamDispatcher();
    const handler = vi.fn();

    dispatcher.on('tool_call', handler);
    dispatcher.off('tool_call', handler);
    dispatcher.emit('tool_call', '{}', null);

    expect(handler).not.toHaveBeenCalled();
  });

  it('does not fail emitting to unregistered event', () => {
    const dispatcher = new StreamDispatcher();
    expect(() => dispatcher.emit('content', 'data', null)).not.toThrow();
  });

  it('handles errors in handlers gracefully', () => {
    const dispatcher = new StreamDispatcher();
    const badHandler = () => { throw new Error('handler error'); };
    const goodHandler = vi.fn();

    dispatcher.on('content', badHandler);
    dispatcher.on('content', goodHandler);

    expect(() => dispatcher.emit('content', 'data', null)).not.toThrow();
    expect(goodHandler).toHaveBeenCalled();
  });

  it('removeAll clears all handlers', () => {
    const dispatcher = new StreamDispatcher();
    const handler = vi.fn();

    dispatcher.on('content', handler);
    dispatcher.on('reasoning', handler);
    dispatcher.removeAll();

    dispatcher.emit('content', 'd', null);
    dispatcher.emit('reasoning', 'd', null);

    expect(handler).not.toHaveBeenCalled();
  });

  it('is generic — typed context is preserved', () => {
    type Ctx = { id: number };
    const dispatcher = new StreamDispatcher<Ctx>();
    const handler = vi.fn();

    dispatcher.on('error', handler);
    dispatcher.emit('error', 'err', { id: 1 });

    expect(handler).toHaveBeenCalledWith('err', { id: 1 });
  });
});
