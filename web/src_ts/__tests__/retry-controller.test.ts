import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { RetryController } from '../core/ui/RetryHandler';

describe('RetryController contract', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts with count 0', () => {
    const rc = new RetryController();
    expect(rc.count).toBe(0);
  });

  it('shouldRetry returns true when count < maxRetries and no content', () => {
    const rc = new RetryController();
    expect(rc.shouldRetry(false)).toBe(true);
  });

  it('shouldRetry returns false when count >= maxRetries', () => {
    const rc = new RetryController();
    rc.count = 3;
    expect(rc.shouldRetry(false)).toBe(false);
  });

  it('shouldRetry returns false when hasContent is true', () => {
    const rc = new RetryController();
    expect(rc.shouldRetry(true)).toBe(false);
  });

  it('resetRetryCount resets count to 0', () => {
    const rc = new RetryController();
    rc.count = 2;
    rc.resetRetryCount();
    expect(rc.count).toBe(0);
  });

  it('scheduleRetry increments count', () => {
    const rc = new RetryController();
    const assistantEl = document.createElement('div');
    const onRetry = vi.fn();

    rc.scheduleRetry({ assistantEl, userText: 'hello', reason: 'error', onRetry });
    expect(rc.count).toBe(1);
  });

  it('scheduleRetry preserves completed reasoning and tool calls', () => {
    const rc = new RetryController();
    const assistantEl = document.createElement('div');
    const reasoning = document.createElement('div');
    reasoning.className = 'reasoning';
    assistantEl.appendChild(reasoning);
    const toolCalls = document.createElement('div');
    toolCalls.className = 'tool-calls';
    assistantEl.appendChild(toolCalls);
    const onRetry = vi.fn();

    rc.scheduleRetry({ assistantEl, userText: 'hello', reason: 'error', onRetry });

    expect(assistantEl.querySelector('.reasoning')).toBe(reasoning);
    expect(assistantEl.querySelector('.tool-calls')).toBe(toolCalls);
  });

  it('renders the retry boundary with error and attempt metadata', () => {
    const rc = new RetryController();
    const assistantEl = document.createElement('div');

    rc.showRetryCheckpoint({
      assistantEl,
      attempt: 2,
      maxRetries: 3,
      reason: 'provider disconnected',
      state: 'active',
    });

    const card = assistantEl.querySelector('.retry-checkpoint');
    expect(card?.textContent).toContain('Reanudación desde checkpoint');
    expect(card?.textContent).toContain('Intento 2/3');
    expect(card?.textContent).toContain('provider disconnected');
    expect(card?.classList.contains('retry-checkpoint--active')).toBe(true);
  });

  it('marks the active retry as completed without removing prior phases', () => {
    const rc = new RetryController();
    const assistantEl = document.createElement('div');
    const phase = document.createElement('div');
    phase.dataset.phase = '4';
    assistantEl.appendChild(phase);
    rc.showRetryCheckpoint({
      assistantEl,
      attempt: 1,
      reason: 'network',
      state: 'active',
    });

    rc.markRetryCompleted(assistantEl);

    expect(assistantEl.querySelector('[data-phase="4"]')).toBe(phase);
    expect(assistantEl.querySelector('.retry-checkpoint--completed')).not.toBeNull();
  });

  it('scheduleRetry calls onRetry after delay', () => {
    const rc = new RetryController();
    const assistantEl = document.createElement('div');
    const onRetry = vi.fn();

    rc.scheduleRetry({ assistantEl, userText: 'hello', reason: 'error', onRetry });
    expect(onRetry).not.toHaveBeenCalled();

    vi.advanceTimersByTime(2100);
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onRetry).toHaveBeenCalledWith(1);
  });

  it('getStreamTimeout returns default 300000', () => {
    const rc = new RetryController();
    expect(rc.getStreamTimeout()).toBe(300000);
  });

  it('getStreamTimeout uses custom timeout if set', () => {
    const rc = new RetryController();
    rc.streamTimeout = 30000;
    expect(rc.getStreamTimeout()).toBe(30000);
  });

  it('maxRetries defaults to 3', () => {
    const rc = new RetryController();
    expect(rc.maxRetries).toBe(3);
  });
});
