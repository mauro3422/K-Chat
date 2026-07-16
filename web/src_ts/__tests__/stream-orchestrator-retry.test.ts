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
    const handleChatSend = vi.fn(async () => {});
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
    const retryPrompt = ((handleChatSend.mock.calls[0] as unknown) as [string, string | undefined, number | undefined])[0];
    expect(retryPrompt).toContain('Retry attempt 2/3');
    expect(retryPrompt).toContain('timeout');
    expect(retryPrompt).toContain('Mensaje original');
  });
});
