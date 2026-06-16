import { IEventBus } from '../types/events';
import { IWidgetRegistry } from '../types/widgets';
import { IIframeBuilder } from '../types/iframe';
import { IWidgetContainerRenderer } from '../types/widget-renderer';
import { IDebugManager } from '../types/debug';
import { SSEEvent, SSENewMessage, SSEStreamReasoning, SSEStreamContent, SSEStreamTool, SSEStreamMemory, SSEStreamError } from '../types/sse';
import { StreamDispatcher } from './StreamDispatcher';
import { ContentHandler, StreamHandlerContext } from './ContentHandler';
import { IMessageView } from '../types/message-view';
import { MessageData } from '../rendering/MessageView';
import { getLogger } from '../core/LoggerFactory';
import { ILogger } from '../core/Logger';

export interface ISSEClient {
  connect(): void;
  disconnect(): void;
  setCurrentSessionId(sid: string | null): void;
  setLoadingSession(loading: boolean): void;
}

/**
 * SSEClient — connects to /api/events/stream via EventSource.
 *
 * Handles two families of events:
 * 1. stream:* events — live Telegram tokens, rendered via ContentHandler
 * 2. session events — new_message, session_deleted, message_deleted
 *
 * The production reference is web/static/modules/sse-client.js.
 */
export class SSEClient implements ISSEClient {
  private eventSource: EventSource | null = null;
  private currentSessionId: string | null = null;
  private loadingSession = false;
  private logger: ILogger;

  // Live message state (for Telegram streaming via SSE)
  private liveMsgEl: HTMLElement | null = null;
  private liveDispatcher: StreamDispatcher<StreamHandlerContext> | null = null;
  private liveContentHandler: ContentHandler | null = null;
  private liveContext: StreamHandlerContext | null = null;
  private liveSessionId: string | null = null;

  constructor(
    private eventBus: IEventBus,
    private messageView: IMessageView,
    private iframeBuilder: IIframeBuilder,
    private containerRenderer: IWidgetContainerRenderer,
    private widgetRegistry: IWidgetRegistry,
    private debug?: IDebugManager,
  ) {
    this.logger = getLogger('sse-client');
  }

  connect(): void {
    if (this.eventSource) return;
    this.logger.info('Connecting to SSE /api/events/stream');
    this.eventSource = new EventSource('/api/events/stream');
    this.eventSource.onmessage = (e: MessageEvent) => this.handleMessage(e);
    this.eventSource.onerror = () => {
      this.debug?.logUI('sse', 'Connection error (will auto-reconnect)');
    };
  }

  disconnect(): void {
    this.eventSource?.close();
    this.eventSource = null;
    this.clearLiveMessage();
  }

  setCurrentSessionId(sid: string | null): void {
    this.currentSessionId = sid;
  }

  setLoadingSession(loading: boolean): void {
    this.loadingSession = loading;
  }

  private handleMessage(e: MessageEvent): void {
    let event: SSEEvent;
    try {
      event = JSON.parse(e.data) as SSEEvent;
    } catch {
      return;
    }

    switch (event.type) {
      case 'ping':
        break;
      case 'stream:reasoning':
        this.handleStreamReasoning(event.data);
        break;
      case 'stream:content':
        this.handleStreamContent(event.data);
        break;
      case 'stream:tool':
        this.handleStreamTool(event.data);
        break;
      case 'stream:memory':
        this.handleStreamMemory(event.data);
        break;
      case 'stream:error':
        this.handleStreamError(event.data);
        break;
      case 'new_message':
        this.handleNewMessage(event.data);
        break;
      case 'session_deleted':
        this.handleSessionDeleted(event.data);
        break;
      case 'message_deleted':
        this.handleMessageDeleted(event.data);
        break;
    }
  }

  // ── Stream handlers (Telegram live tokens) ────────────

  private handleStreamReasoning(data: SSEStreamReasoning): void {
    if (data.session_id !== this.currentSessionId) return;
    this.ensureLiveMessage(data.session_id);
    this.liveDispatcher?.emit('reasoning', data.text, this.liveContext!);
  }

  private handleStreamContent(data: SSEStreamContent): void {
    if (data.session_id !== this.currentSessionId) return;
    this.ensureLiveMessage(data.session_id);
    this.liveDispatcher?.emit('content', data.text, this.liveContext!);
  }

  private handleStreamTool(data: SSEStreamTool): void {
    if (data.session_id !== this.currentSessionId) return;
    this.ensureLiveMessage(data.session_id);
    const payload = JSON.stringify({
      name: data.tool_name,
      status: data.status,
      id: data.tool_id,
    });
    this.liveDispatcher?.emit('tool_call', payload, this.liveContext!);
  }

  private handleStreamMemory(data: SSEStreamMemory): void {
    if (data.session_id !== this.currentSessionId) return;
    this.ensureLiveMessage(data.session_id);
    this.liveDispatcher?.emit('memory', data.text, this.liveContext!);
  }

  private handleStreamError(data: SSEStreamError): void {
    if (data.session_id !== this.currentSessionId) return;
    this.ensureLiveMessage(data.session_id);
    const payload = JSON.stringify({
      type: 'stream_error',
      message: data.error,
    });
    this.liveDispatcher?.emit('error', payload, this.liveContext!);
  }

  /**
   * Ensure a live message element exists for the given session.
   * Creates a new one if none exists or if the session changed.
   */
  private ensureLiveMessage(sessionId: string): void {
    if (this.liveSessionId === sessionId && this.liveMsgEl?.parentNode) return;

    // Clear previous live message for a different session
    this.clearLiveMessage();
    this.liveSessionId = sessionId;

    // Create new assistant live message via MessageView
    const msgEl = this.messageView.beginStreaming('assistant');
    if (!msgEl) return;
    this.liveMsgEl = msgEl;
    msgEl.dataset.sessionId = sessionId;

    // Create content handler pipeline for this live message
    const dispatcher = new StreamDispatcher<StreamHandlerContext>();
    const contentHandler = new ContentHandler(
      dispatcher,
      this.iframeBuilder,
      this.containerRenderer,
      this.widgetRegistry,
      this.debug,
    );
    this.liveDispatcher = dispatcher;
    this.liveContentHandler = contentHandler;
    this.liveContext = contentHandler.createContext(msgEl);

    this.containerRenderer.reset();
  }

  /** Clear the current live message and its pipeline */
  private clearLiveMessage(): void {
    if (this.liveMsgEl) {
      this.liveMsgEl.classList.remove('streaming', 'live-msg');
    }
    this.liveMsgEl = null;
    this.liveDispatcher = null;
    this.liveContentHandler = null;
    this.liveContext = null;
    this.liveSessionId = null;
  }

  // ── Session event handlers ───────────────────────────

  private handleNewMessage(data: SSENewMessage): void {
    const sid = data.session_id;
    if (!sid) return;

    // Clean up any live message for this session
    if (sid === this.currentSessionId) {
      this.clearLiveMessage();
    }

    const msgData: MessageData = {
      role: data.role,
      content: data.content,
      ts: data.ts,
      reasoning: data.reasoning,
    };

    // Parse phases if present (JSON string → array)
    if (data.phases) {
      try {
        const parsed = JSON.parse(data.phases);
        if (Array.isArray(parsed)) {
          (msgData as any).phases = parsed;
        }
      } catch { /* ignore invalid JSON */ }
    }

    if (sid === this.currentSessionId) {
      // Active session — append directly
      if (!this.loadingSession) {
        this.messageView.appendMessage(msgData);
      }
    }

    // Always emit event for session store and sidebar
    this.eventBus.emit('sse:new-message', {
      sessionId: sid,
      message: msgData,
      isCurrentSession: sid === this.currentSessionId,
    });
  }

  private handleSessionDeleted(data: { session_id: string }): void {
    this.eventBus.emit('sse:session-deleted', { id: data.session_id });
  }

  private handleMessageDeleted(data: { session_id: string; message_id: number }): void {
    this.eventBus.emit('sse:message-deleted', {
      sessionId: data.session_id,
      messageId: data.message_id,
    });

    // Direct DOM removal if it's the current session
    if (data.session_id === this.currentSessionId) {
      const msgEl = document.querySelector(`.msg[data-id="${data.message_id}"]`) as HTMLElement | null;
      if (msgEl) {
        msgEl.style.transition = 'opacity 0.3s';
        msgEl.style.opacity = '0';
        setTimeout(() => msgEl.remove(), 350);
      }
    }
  }
}
