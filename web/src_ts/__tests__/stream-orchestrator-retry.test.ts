import { describe, it, expect, vi } from 'vitest';
import { StreamOrchestrator } from '../streaming/StreamOrchestrator';
import { RetryController } from '../core/ui/RetryHandler';

function makeOrchestrator(retryController: RetryController) {
  const messageView = {
    init: vi.fn(),
    appendMessage: vi.fn(),
    beginStreaming: vi.fn(),
    endStreaming: vi.fn(),
    clearContainer: vi.fn(),
  };
  const streamSimulator = {
    detectIntent: vi.fn(() => ({ intent: 'chat', includeWidget: false })),
    generate: vi.fn(),
  };
  const sessionStore = {
    activeSessionId: 'session-1',
    sessions: [],
    createSession: vi.fn(),
    renameSession: vi.fn(),
    addMessage: vi.fn(),
  };
  const chatForm = { init: vi.fn(), setStreamingState: vi.fn() };
  const iframeBuilder = {};
  const containerRenderer = { reset: vi.fn() };
  const widgetRegistry = {};
  const renderMarkdown = (markdown: string) => markdown;
  const rateLimitCooldown = {
    canSubmit: vi.fn(() => true),
    cancel: vi.fn(),
    start: vi.fn(),
    remainingSec: 0,
  };

  return new StreamOrchestrator(
    messageView as any,
    streamSimulator as any,
    sessionStore as any,
    chatForm as any,
    iframeBuilder as any,
    containerRenderer as any,
    widgetRegistry as any,
    renderMarkdown,
    rateLimitCooldown as any,
    undefined,
    retryController,
    undefined,
    undefined,
  );
}

describe('StreamOrchestrator retry prompt', () => {
  it('preserves the scheduled attempt number after abort resets internal counters', async () => {
    const retryController = new RetryController();
    retryController.count = 1;

    const orchestrator = makeOrchestrator(retryController);
    const handleChatSend = vi.fn(async (text: string) => {
      expect(text).toBe('Mensaje original');
      expect((orchestrator as any)._retryRequest).toEqual({
        resume: true,
        errorType: 'timeout',
        errorMessage: 'La respuesta tardó demasiado',
        retryCount: 2,
      });
    });
    const abort = vi.fn(() => {
      retryController.resetRetryCount();
    });

    (orchestrator as any).handleChatSend = handleChatSend;
    (orchestrator as any).abort = abort;
    (orchestrator as any)._lastError = { type: 'timeout', message: 'La respuesta tardó demasiado' };
    (orchestrator as any).currentModel = 'gpt-4';
    (orchestrator as any).lastAssistantMsgEl = null;

    await orchestrator.handleRetry('Mensaje original', 'gpt-4', 2);

    expect(abort).toHaveBeenCalledOnce();
    expect(handleChatSend).toHaveBeenCalledOnce();
  });

  it('falls back to the first retry attempt when the counter has been cleared', async () => {
    const retryController = new RetryController();

    const orchestrator = makeOrchestrator(retryController);
    const handleChatSend = vi.fn(async (text: string) => {
      expect(text).toBe('Mensaje original');
      expect((orchestrator as any)._retryRequest).toEqual({
        resume: true,
        errorType: 'rate_limit',
        errorMessage: 'límite alcanzado',
        retryCount: 1,
      });
    });

    (orchestrator as any).handleChatSend = handleChatSend;
    (orchestrator as any)._lastError = { type: 'rate_limit', message: 'límite alcanzado' };
    (orchestrator as any).abort = vi.fn(() => {
      retryController.resetRetryCount();
    });

    await orchestrator.handleRetry('Mensaje original', 'gpt-4');

  });

  it('reuses the preserved bubble and keeps prior phases after the retry delay', async () => {
    const retryController = new RetryController();
    const orchestrator = makeOrchestrator(retryController);
    const assistantEl = document.createElement('article');
    const priorPhase = document.createElement('div');
    priorPhase.className = 'msg-body';
    priorPhase.dataset.phase = '3';
    priorPhase.textContent = 'Trabajo ya completado';
    assistantEl.appendChild(priorPhase);
    retryController.showRetryCheckpoint({
      assistantEl,
      attempt: 1,
      reason: 'provider desconectado',
      state: 'waiting',
    });

    (orchestrator as any)._lastError = {
      type: 'network',
      message: 'provider desconectado',
    };
    (orchestrator as any)._retryBubbleEl = assistantEl;
    (orchestrator as any).lastAssistantMsgEl = null;
    (orchestrator as any).abort = vi.fn();
    (orchestrator as any).handleChatSend = vi.fn(async () => {
      expect((orchestrator as any).lastAssistantMsgEl).toBe(assistantEl);
      expect(assistantEl.querySelector('[data-phase="3"]')?.textContent)
        .toBe('Trabajo ya completado');
      expect(assistantEl.querySelector('.retry-checkpoint--active')).not.toBeNull();
    });

    await orchestrator.handleRetry('Mensaje original', 'gpt-4', 1);

    expect((orchestrator as any).handleChatSend).toHaveBeenCalledOnce();
  });
});
