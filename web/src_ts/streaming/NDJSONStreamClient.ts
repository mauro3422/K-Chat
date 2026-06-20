import { IStreamDispatcher } from '../types/dispatcher';
import { ApiClient } from '../api/ApiClient';
import { StreamEvent, StreamEventType, STREAM_EVENT_TYPES } from '../types/streaming';
import { IEventBus } from '../types/events';
import { getLogger } from '../core/infra/LoggerFactory';
import { ILogger } from '../core/infra/Logger';

/** Pre-built set of valid stream event types — avoid `new Set()` on every parse */
const VALID_EVENT_TYPES = new Set(Object.values(STREAM_EVENT_TYPES));

export interface StreamParams {
  sessionId: string;
  message: string;
  model?: string;
  signal?: AbortSignal;
  dispatcher: IStreamDispatcher<unknown>;
  context: unknown;
  onFirstToken?: () => void;
  onChunk?: () => void;
  files?: File[];
}

export interface INDJSONStreamClient {
  startStream(params: StreamParams): Promise<void>;
  abort(): void;
  readonly isStreaming: boolean;
}

function parseStreamEvent(raw: string): StreamEvent | null {
  if (!raw) return null;
  let msg: Record<string, unknown>;
  try {
    msg = JSON.parse(raw) as Record<string, unknown>;
  } catch {
    return null;
  }
  if (!msg || typeof msg !== 'object') return null;
  if (typeof msg.t !== 'string') return null;
  if (!VALID_EVENT_TYPES.has(msg.t as StreamEventType)) return null;
  return { t: msg.t as StreamEventType, d: String(msg.d ?? '') };
}

export class NDJSONStreamClient implements INDJSONStreamClient {
  private apiClient: ApiClient;
  private eventBus?: IEventBus;
  private logger: ILogger;
  private _isStreaming = false;
  private controller: AbortController | null = null;
  private externalSignal: AbortSignal | null = null;
  private onExternalAbort: (() => void) | null = null;

  constructor(apiClient: ApiClient, eventBus?: IEventBus) {
    this.apiClient = apiClient;
    this.eventBus = eventBus;
    this.logger = getLogger('sse');
  }

  get isStreaming(): boolean {
    return this._isStreaming;
  }

  async startStream(params: StreamParams): Promise<void> {
    if (this._isStreaming) {
      throw new Error('NDJSONStreamClient: already streaming');
    }

    this._isStreaming = true;
    this.controller = new AbortController();
    this.externalSignal = params.signal || null;
    this.logger.info('stream start', { sessionId: params.sessionId, model: params.model });

    if (this.externalSignal) {
      this.onExternalAbort = () => this.controller?.abort();
      this.externalSignal.addEventListener('abort', this.onExternalAbort);

      if (this.externalSignal.aborted) {
        this.controller.abort();
      }
    }

    try {
      await this.executeStream(params);
    } finally {
      this.cleanup();
    }
  }

  abort(): void {
    this.controller?.abort();
  }

  private cleanup(): void {
    this._isStreaming = false;
    if (this.externalSignal && this.onExternalAbort) {
      this.externalSignal.removeEventListener('abort', this.onExternalAbort);
    }
    this.controller = null;
    this.externalSignal = null;
    this.onExternalAbort = null;
  }

  private async executeStream(params: StreamParams): Promise<void> {
    const { sessionId, message, model, dispatcher, context, onFirstToken, onChunk, files } = params;
    const controller = this.controller!;

    let resp: Response;
    try {
      if (files && files.length > 0) {
        resp = await this.apiClient.chatStreamWithFiles(sessionId, message, model || 'default', controller, files);
      } else {
        resp = await this.apiClient.chatStream(sessionId, message, model || 'default', controller);
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (err instanceof Error && err.message.toLowerCase().includes('aborted')) return;
      dispatcher.emit('error', JSON.stringify({ type: 'network', message: 'Connection failed' }), context);
      return;
    }

    if (resp.status === 401) {
      dispatcher.emit('error', JSON.stringify({ type: 'auth', message: 'Error de autenticación. Verifica tu API key.' }), context);
      return;
    }
    if (resp.status === 429) {
      dispatcher.emit('error', JSON.stringify({ type: 'rate_limit', message: 'Límite de tasa alcanzado. Espera un momento.' }), context);
      this.eventBus?.emit('rate-limit:detected', { duration: 60000 });
      return;
    }
    if (resp.status >= 500) {
      dispatcher.emit('error', JSON.stringify({ type: 'server', message: `Error del servidor (${resp.status})` }), context);
      return;
    }
    if (!resp.ok) {
      dispatcher.emit('error', JSON.stringify({ type: 'http', message: `HTTP ${resp.status}` }), context);
      return;
    }
    if (!resp.body) {
      dispatcher.emit('error', JSON.stringify({ type: 'network', message: 'Response body is null' }), context);
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '';
    let firstToken = true;

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          buf += decoder.decode();
          if (buf.trim()) {
            const ev = parseStreamEvent(buf.trim());
            if (ev) {
              dispatcher.emit(ev.t, ev.d, context);
            }
          }
          return;
        }

        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n');
        buf = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;

          const ev = parseStreamEvent(line);
          if (!ev) continue;
          if (ev.t === 'heartbeat') {
            if (onChunk) onChunk();
            continue;
          }

          if (firstToken && (ev.t === 'content' || ev.t === 'reasoning')) {
            firstToken = false;
            if (onFirstToken) onFirstToken();
          }

          dispatcher.emit(ev.t, ev.d, context);
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      if (err instanceof Error && err.message.toLowerCase().includes('aborted')) return;
      dispatcher.emit('error', JSON.stringify({ type: 'network', message: 'Connection failed' }), context);
    }
  }
}
