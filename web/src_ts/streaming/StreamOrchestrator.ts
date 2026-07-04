import { StreamDispatcher } from './StreamDispatcher';
import { ContentHandler, StreamHandlerContext } from './ContentHandler';
import { StreamSimulator } from './StreamSimulator';
import { NDJSONStreamClient } from './NDJSONStreamClient';
import type { MessageData } from '../types/messages';
import { IMessageView } from '../types/message-view';
import { IChatForm } from '../types/chat-form';
import { RateLimitCooldown } from '../core/notification/RateLimitCooldown';
import { SessionStore } from '../core/session/SessionStore';
import { IDebugManager } from '../types/debug';
import { IRetryController } from '../core/ui/RetryHandler';
import { WidgetContainerRenderer } from '../rendering/WidgetContainerRenderer';
import { WidgetRegistry } from '../core/widget/WidgetRegistry';
import { IframeBuilder } from '../rendering/IframeBuilder';
import { getLogger } from '../core/infra/LoggerFactory';
import { ILogger } from '../core/infra/Logger';
import { C } from '../core/infra/DomContracts';
import { IEventBus } from '../types/events';

export { type StreamHandlerContext } from './ContentHandler';

export interface IStreamOrchestrator {
  handleChatSend(text: string, files?: File[], model?: string): Promise<void>;
  abort(): void;
  handleRetry(text: string, model?: string): void;
}

export class StreamOrchestrator implements IStreamOrchestrator {
  private _streamGuard = false;
  private _lastStartMs = 0;
  private _streamTimeout: number | null = null;
  private readonly STREAM_TIMEOUT_MS = 120000;
  private _pendingTimeout = false;
  private _hasReasoning = false;
  private _hasToolCalls = false;
  private _hasContent = false;

  private activeContext: StreamHandlerContext | null = null;
  private lastAssistantMsgEl: HTMLElement | null = null;
  private abortStreamFn: (() => void) | null = null;
  private abortController: AbortController | null = null;
  private currentUserText: string | null = null;
  private currentModel: string | null = null;
  private contentHandler: ContentHandler | null = null;
  private _isRetry = false;
  private logger: ILogger;

  constructor(
    private messageView: IMessageView,
    private streamSimulator: StreamSimulator,
    private sessionStore: SessionStore,
    private chatForm: IChatForm,
    private iframeBuilder: IframeBuilder,
    private containerRenderer: WidgetContainerRenderer,
    private widgetRegistry: WidgetRegistry,
    private renderMarkdown: (markdown: string) => string,
    private rateLimitCooldown: RateLimitCooldown,
    private debug?: IDebugManager,
    private retryController?: IRetryController,
    private ndjsonClient?: NDJSONStreamClient,
    private eventBus?: IEventBus,
  ) {
    this.logger = getLogger('stream-orch');
  }

  get isStreaming(): boolean {
    return this.activeContext !== null;
  }

  get debugActiveContext(): StreamHandlerContext | null {
    return this.activeContext;
  }

  get debugLastAssistantMsgEl(): HTMLElement | null {
    return this.lastAssistantMsgEl;
  }

  async handleChatSend(text: string, files?: File[], model?: string): Promise<void> {
    const now = Date.now();
    if (now - this._lastStartMs < 500) {
      this.debug?.logUI('stream_guard', `temporal guard (${now - this._lastStartMs}ms)`);
      return;
    }
    if (this._streamGuard) {
      this.debug?.logUI('stream_guard', 'boolean guard (already streaming)');
      return;
    }

    if (!this.rateLimitCooldown.canSubmit()) return;
    if (!text.trim() && (!files || files.length === 0)) return;

    this._streamGuard = true;
    this._lastStartMs = now;
    this._hasReasoning = false;
    this._hasToolCalls = false;
    this._hasContent = false;

    if (files && files.length > 0) {
      this.logger.info('files attached', files.map(f => `${f.name} (${f.size} bytes)`));
    }

    const intent = this.streamSimulator.detectIntent(text);
    this.debug?.logUI('send_message', `"${text.substring(0, 40)}" → intent:${intent.intent} widget:${intent.includeWidget}`);

    this.currentUserText = text;
    this.currentModel = model || null;

    // Ensure there's an active session before sending
    if (!this.sessionStore.activeSessionId) {
      const newId = await this.sessionStore.createSession();
      if (!newId) {
        this._streamGuard = false;
        this.chatForm.setStreamingState(false);
        this.debug?.logUI('send_error', 'failed to create session');
        return;
      }
      this.debug?.logUI('session_created', newId);
      this.sessionStore.renameSession(newId, text.substring(0, 60));
    }

    if (!this._isRetry) {
      const userMsg: MessageData = { role: 'user', content: text, ts: new Date().toISOString() };
      this.messageView.appendMessage(userMsg);
      this.sessionStore.addMessage(this.sessionStore.activeSessionId, userMsg);
    }
    this.chatForm.setStreamingState(true);

    const assistantEl = this.messageView.beginStreaming('assistant');
    if (!assistantEl) {
      this._streamGuard = false;
      this.chatForm.setStreamingState(false);
      return;
    }

    assistantEl.dataset.userText = text;

    const dispatcher = new StreamDispatcher<StreamHandlerContext>();
    this.contentHandler = new ContentHandler(
      dispatcher, this.iframeBuilder, this.containerRenderer, this.widgetRegistry, this.renderMarkdown, this.debug,
    );

    let streamError: { type: string; message: string } | null = null;

    dispatcher.on('reasoning', () => {
      this._hasReasoning = true;
      this._resetTimeout();
    });
    dispatcher.on('content', () => {
      this._hasContent = true;
      this._resetTimeout();
    });
    dispatcher.on('tool_call', () => {
      this._hasToolCalls = true;
      this._resetTimeout();
    });
    dispatcher.on('memory', () => this._resetTimeout());
    dispatcher.on('notification', (data) => {
      try {
        const parsed = JSON.parse(data);
        const id = 'notif-' + Date.now();
        this.eventBus?.emit('notification:show', {
          id,
          type: parsed.type || 'info',
          message: parsed.message || '',
          duration: parsed.duration ?? 5000,
        });
      } catch { /* ignore malformed notification */ }
      this._resetTimeout();
    });
    dispatcher.on('error', (data) => {
      try {
        const raw = typeof data === 'string' ? data : JSON.stringify(data);
        let parsed: Record<string, string>;
        try {
          parsed = JSON.parse(raw);
        } catch {
          parsed = { type: 'unknown', message: raw };
        }
        const errType = parsed.type || 'unknown';
        const errMsg = String(parsed.message || (parsed.error ? (typeof parsed.error === 'string' ? parsed.error : JSON.stringify(parsed.error)) : 'Error desconocido'));
        streamError = { type: errType, message: errMsg };
        // Surface rate_limit/auth errors immediately
        if (errType === 'rate_limit' || errType === 'auth' || errType === 'quota' || errType === 'insufficient_quota') {
          this._handleStreamError(errType, errMsg);
        }
      } catch {
        streamError = { type: 'unknown', message: typeof data === 'string' ? data : String(data || 'Error de conexión') };
      }
      this._resetTimeout();
    });

    const ctx = this.contentHandler.createContext(assistantEl);
    this.activeContext = ctx;
    this.lastAssistantMsgEl = assistantEl;

    this.containerRenderer.reset();
    this._startTimeout();

    if (this.ndjsonClient) {
      // ── REAL BACKEND MODE ──
      const abortController = new AbortController();
      this.abortController = abortController;

      this.abortStreamFn = () => {
        abortController.abort();
        this.ndjsonClient?.abort();
      };

      try {
        await this.ndjsonClient.startStream({
          sessionId: this.sessionStore.activeSessionId,
          message: text,
          model: model || '',
          signal: abortController.signal,
          dispatcher: dispatcher,
          context: ctx,
          onFirstToken: () => {
            this.debug?.logUI('first_token', 'received');
            if (this.lastAssistantMsgEl) {
              const bodyEl = this.lastAssistantMsgEl.querySelector('.' + C.MSG_BODY);
              if (bodyEl && bodyEl.textContent?.trim() === '✍️ Pensando...') {
                bodyEl.textContent = '';
              }
            }
          },
        });
      } catch (err: unknown) {
        if (err instanceof Error && (
          err.name === 'AbortError' ||
          err.message.toLowerCase().includes('abort') ||
          err.message.includes('already streaming')
        )) {
          return;
        }
        const errMsg = err instanceof Error ? err.message : typeof err === 'string' ? err : JSON.stringify(err);
        this.debug?.logUI('stream_error', `Backend error: ${errMsg}`);
      }

      this.abortController = null;
      this._relabelReasoning(assistantEl);
      this._handleStreamCompletion(ctx, assistantEl, streamError);
    } else {
      // ── SIMULATOR MODE ──
      const events = this.streamSimulator.generate(text);
      let idx = 0;
      let aborted = false;
      const timeoutIds: number[] = [];

      this.abortStreamFn = () => {
        if (aborted) return;
        aborted = true;
        timeoutIds.forEach(id => clearTimeout(id));
        timeoutIds.length = 0;
      };

      const playNext = () => {
        if (aborted) return;

        if (idx >= events.length) {
          this._clearTimeout();
          this._relabelReasoning(assistantEl);
          this._handleStreamCompletion(ctx, assistantEl, streamError);
          return;
        }

        const ev = events[idx];
        idx++;

        dispatcher.emit(ev.t, ev.d, ctx);

        let delay = 30 + Math.random() * 60;

        if (ev.t === 'tool_call') {
          try {
            const payload = JSON.parse(ev.d);
            delay = payload.status === 'calling' ? 800 : 200;
          } catch { delay = 200; }
        } else if (ev.t === 'content' && ev.d.includes('\n')) {
          delay = 200 + Math.random() * 200;
        } else if (ev.t === 'heartbeat') {
          delay = 1;
        } else if (ev.t === 'memory') {
          delay = 40 + Math.random() * 80;
        } else {
          this.debug?.logUI('stream_unknown_event', String(ev.t));
        }

        const id = window.setTimeout(playNext, delay);
        timeoutIds.push(id);
      };

      playNext();
    }
  }

  abort(): void {
    if (!this._streamGuard) return;

    this._clearTimeout();
    this._streamGuard = false;

    this.ndjsonClient?.abort();
    this.abortController?.abort();
    this.abortController = null;

    if (this.abortStreamFn) {
      this.abortStreamFn();
    }

    if (this.lastAssistantMsgEl) {
      const body = this.lastAssistantMsgEl.querySelector('.' + C.MSG_BODY);
      const hasContent = body && body.textContent && body.textContent.trim().length > 0;
      const hasReasoning = this.lastAssistantMsgEl.querySelector('.' + C.REASONING);
      if (!hasContent && !hasReasoning) {
        this.lastAssistantMsgEl.remove();
      }
      this.lastAssistantMsgEl.classList.remove('streaming', 'live-msg');
    }
    this.lastAssistantMsgEl = null;

    this.activeContext = null;
    this.contentHandler = null;
    this.retryController?.resetRetryCount();
    this.chatForm.setStreamingState(false);
    this.debug?.logUI('stream_aborted', 'cancelado por usuario');
  }

  handleRetry(text: string, model?: string): void {
    this.abort();
    this.chatForm.setStreamingState(false);
    this.ndjsonClient?.abort();
    this._isRetry = true;
    this.handleChatSend(text, undefined, model || (this.currentModel ?? undefined));
    this._isRetry = false;
  }

  private _relabelReasoning(assistantEl: HTMLElement): void {
    const reasoningEls = assistantEl.querySelectorAll('.' + C.REASONING);
    if (reasoningEls.length > 0) {
      const lastSummary = reasoningEls[reasoningEls.length - 1].querySelector('summary');
      if (lastSummary) lastSummary.textContent = 'Razonamiento';
    }
  }

  private _startTimeout(): void {
    this._clearTimeout();
    this._streamTimeout = window.setTimeout(() => {
      this.debug?.logUI('stream_timeout', 'idle timeout reached (120s)');
      if (this.abortStreamFn) this.abortStreamFn();
      this._handleStreamError('timeout', 'La respuesta tardó demasiado');
    }, this.STREAM_TIMEOUT_MS);
  }

  private _resetTimeout(): void {
    if (this._pendingTimeout) return;
    this._pendingTimeout = true;
    requestAnimationFrame(() => {
      this._pendingTimeout = false;
      this._startTimeout();
    });
  }

  private _clearTimeout(): void {
    if (this._streamTimeout !== null) {
      clearTimeout(this._streamTimeout);
      this._streamTimeout = null;
    }
  }

  private _handleStreamError(type: string, message: string): void {
    this._clearTimeout();

    // Guard: prevent double-invocation after stream already finalized
    if (!this._streamGuard) return;

    if (type === 'auth' || type === 'rate_limit' || type === 'bad_request') {
      this._showErrorCard(type, message);
      this.debug?.logUI('stream_error_terminal', `${type}: ${message}`);
      this.retryController?.resetRetryCount();
      this._finalizeStream();
      return;
    }

    if (this.retryController?.shouldRetry(false) && this.currentUserText) {
      const text = this.currentUserText;
      this.debug?.logUI('stream_error_retry', `${type}: ${message} — attempt ${this.retryController.count + 1}/${this.retryController.maxRetries}`);
        this.retryController.scheduleRetry({
          assistantEl: this.lastAssistantMsgEl!,
          userText: text,
          reason: message,
          onRetry: () => this.handleRetry(text, this.currentModel ?? undefined),
        });
        this._finalizeStream();
      return;
    }

    this._showErrorCard(type, message);
    this.debug?.logUI('stream_error_final', `${type}: ${message} — retries exhausted`);
    this.retryController?.resetRetryCount();
    this._finalizeStream();
  }

  private _handleStreamPostError(error: { type: string; message: string }): void {
    this._clearTimeout();

    // Guard: prevent double-invocation after stream already finalized
    if (!this._streamGuard) return;

    if (error.type === 'auth' || error.type === 'rate_limit') {
      this.debug?.logUI('stream_error_terminal', `${error.type}: ${error.message}`);
      this.retryController?.resetRetryCount();
      this._markCallingPillsError();
      this._finalizeStream();
      return;
    }

    if (this.retryController?.shouldRetry(false) && this.currentUserText) {
      const text = this.currentUserText;
      this.debug?.logUI('stream_error_retry', `${error.type}: ${error.message} — attempt ${this.retryController.count + 1}/${this.retryController.maxRetries}`);
      this.retryController.scheduleRetry({
        assistantEl: this.lastAssistantMsgEl!,
        userText: text,
        reason: error.message,
        onRetry: () => this.handleRetry(text, this.currentModel ?? undefined),
      });
      this._finalizeStream();
      return;
    }

    this.debug?.logUI('stream_error_final', `${error.type}: ${error.message} — retries exhausted`);
    this.retryController?.resetRetryCount();
    this._markCallingPillsError();
    this._finalizeStream();
  }

  private _handleSuccessfulStream(): void {
    this.retryController?.resetRetryCount();
    this.debug?.logUI('stream_complete', 'content received, retries reset');
    this.eventBus?.emit('sessions:updated', { sessions: this.sessionStore.sessions, activeId: this.sessionStore.activeSessionId });
    this.debug?.refresh();
    this._finalizeStream();
  }

  private _markCallingPillsError(): void {
    if (this.lastAssistantMsgEl) {
      this.lastAssistantMsgEl.querySelectorAll('.tc-item.calling').forEach(pill => {
        pill.className = pill.className.replace('calling', 'error');
        pill.innerHTML = pill.innerHTML.replace('⚡', '✘');
      });
    }
  }

  private _finalizeStream(): void {
    this._clearTimeout();
    this._streamGuard = false;
    this.activeContext = null;
    this.contentHandler = null;

    if (this.lastAssistantMsgEl) {
      this.lastAssistantMsgEl.classList.remove('streaming', 'live-msg');
    }
    this.lastAssistantMsgEl = null;

    this.chatForm.setStreamingState(false);
  }

  private _handleStreamCompletion(
    ctx: StreamHandlerContext,
    assistantEl: HTMLElement,
    streamError: { type: string; message: string } | null,
  ): void {
    this._clearTimeout();
    assistantEl.classList.remove('streaming', 'live-msg');

    if (streamError) {
      this._handleStreamPostError(streamError);
      return;
    }

    const fullContent = ctx.contentTexts.join('');
    const hasContent = fullContent.trim().length > 0;
    const hadReasoning = ctx.reasoningTexts.length > 0;
    const hadToolCalls = assistantEl.querySelectorAll('.' + C.TC_ITEM).length > 0;

    if (hasContent) {
      this.sessionStore.addMessage(this.sessionStore.activeSessionId, {
        role: 'assistant',
        content: fullContent,
        ts: new Date().toISOString(),
        reasoning: ctx.reasoningTexts.join(' '),
        matched_tools: [],
      });
      this._handleSuccessfulStream();
    } else if (hadReasoning || hadToolCalls) {
      this.debug?.logUI('stream_empty_response', 'reasoning/tool calls present but no content — no retry');
      const bodyEl = ctx.bodyEl || assistantEl.querySelector('.' + C.MSG_BODY) as HTMLElement | null;
      if (bodyEl) {
        const errorCard = document.createElement('div');
        errorCard.className = C.ERROR_CARD;
        errorCard.innerHTML = `
              <div class="${C.ERROR_HEADER}">⚠ Respuesta incompleta</div>
              <div class="${C.ERROR_DETAIL}">El modelo realizó razonamiento o invocó herramientas pero no generó contenido. No se reintentó automáticamente.</div>
            `;
        bodyEl.innerHTML = '';
        bodyEl.appendChild(errorCard);
      }
      this.retryController?.resetRetryCount();
      this._finalizeStream();
    } else if (this.retryController?.shouldRetry(false) && this.currentUserText) {
      const retryText = this.currentUserText;
      this.debug?.logUI('stream_retry', `empty response — attempt ${this.retryController.count + 1}/${this.retryController.maxRetries}`);
      this.retryController.scheduleRetry({
        assistantEl,
        userText: retryText,
        reason: 'empty response',
        onRetry: () => this.handleRetry(retryText, this.currentModel ?? undefined),
      });
      this._finalizeStream();
    } else {
      this.debug?.logUI('stream_empty_final', 'no content, retries exhausted');
      const bodyEl = ctx.bodyEl || assistantEl.querySelector('.' + C.MSG_BODY) as HTMLElement | null;
      if (bodyEl) {
        const errorCard = document.createElement('div');
        errorCard.className = C.ERROR_CARD;
        errorCard.innerHTML = `
              <div class="${C.ERROR_HEADER}">⚠ Respuesta vacía</div>
              <div class="${C.ERROR_DETAIL}">La respuesta estuvo vacía después de reintentos. Puede ser un problema temporal del modelo.</div>
            `;
        bodyEl.innerHTML = '';
        bodyEl.appendChild(errorCard);
      }
      this._finalizeStream();
    }
  }

  private _showErrorCard(type: string, message: string): void {
    const bodyEl = this.activeContext?.bodyEl
      || (this.lastAssistantMsgEl ? this.lastAssistantMsgEl.querySelector('.' + C.MSG_BODY) as HTMLElement : null);

    if (!bodyEl) return;

    bodyEl.innerHTML = '';

    const errorCard = document.createElement('div');
    errorCard.className = C.ERROR_CARD;

    if (type === 'rate_limit') {
      errorCard.classList.add(C.RATE_LIMIT_CARD);
      errorCard.innerHTML = `
        <div class="${C.ERROR_HEADER} rate-limit-header">⏳ Modelo saturado</div>
        <div class="${C.ERROR_DETAIL}">${this._escHtml(message)}</div>
        <div class="${C.ERROR_HINT}">Límite del proveedor, reintentá en unos minutos.</div>
      `;
    } else {
      errorCard.innerHTML = `
        <div class="${C.ERROR_HEADER}">⚠ Respuesta interrumpida</div>
        <div class="${C.ERROR_DETAIL}">${this._escHtml(message)}</div>
      `;
    }

    bodyEl.appendChild(errorCard);
  }

  private _escHtml(str: string): string {
    return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
