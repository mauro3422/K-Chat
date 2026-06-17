import { IEventBus, EventCallback } from '../../types/events';
import { MessageData } from '../../rendering/MessageView';
import { ApiClient } from '../../api/ApiClient';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

export interface ISessionStore {
  readonly sessions: Array<{ id: string; name: string; count: number; last_str: string }>;
  readonly activeSessionId: string;
  readonly activeHistory: MessageData[];

  init(eventBus: IEventBus): Promise<void>;
  createSession(name?: string): Promise<string>;
  deleteSession(id: string): Promise<void>;
  renameSession(id: string, name: string): Promise<void>;
  selectSession(id: string): void;
  addMessage(sessionId: string, msg: MessageData): void;
  getHistory(sessionId: string): MessageData[];
}

export class SessionStore implements ISessionStore {
  private _sessions: Array<{ id: string; name: string; count: number; last_str: string }> = [];
  private _histories: Record<string, MessageData[]> = {};
  private _activeSessionId = '';
  private _eventBus: IEventBus | null = null;
  private _apiClient: ApiClient;
  private _logger: ILogger;
  private _boundListeners: Array<{ event: string; cb: EventCallback<any> }> = [];
  private _loaded = false;

  constructor(apiClient: ApiClient) {
    this._apiClient = apiClient;
    this._logger = getLogger('session-store');
  }

  get sessions() { return this._sessions; }
  get activeSessionId() { return this._activeSessionId; }
  get activeHistory() { return this.getHistory(this._activeSessionId); }

  async init(eventBus: IEventBus): Promise<void> {
    this._eventBus = eventBus;

    const selectCb = (data: { sessionId: string }) => {
      this.selectSession(data.sessionId);
    };
    eventBus.on<{ sessionId: string }>('session:select', selectCb);
    this._boundListeners.push({ event: 'session:select', cb: selectCb });

    const renameCb = async (data: { sessionId: string; name: string }) => {
      await this.renameSession(data.sessionId, data.name);
    };
    eventBus.on<{ sessionId: string; name: string }>('session:rename', renameCb);
    this._boundListeners.push({ event: 'session:rename', cb: renameCb as EventCallback<any> });

    const deleteCb = async (data: { sessionId: string }) => {
      await this.deleteSession(data.sessionId);
    };
    eventBus.on<{ sessionId: string }>('session:delete', deleteCb);
    this._boundListeners.push({ event: 'session:delete', cb: deleteCb as EventCallback<any> });

    // Load sessions from backend
    await this.loadSessions();
  }

  dispose(): void {
    if (this._eventBus) {
      this._boundListeners.forEach(({ event, cb }) => this._eventBus!.off(event, cb));
    }
    this._boundListeners = [];
  }

  async createSession(name?: string): Promise<string> {
    try {
      const resp = await this._apiClient.createSession();
      const data = await resp.json() as { id: string };
      const id = data.id;
      this._sessions.unshift({
        id,
        name: name || id.substring(0, 8),
        count: 0,
        last_str: new Date().toISOString().substring(0, 10),
      });
      this._histories[id] = [];
      this._activeSessionId = id;
      this._emit('session:created', { id });
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
      this._emit('history:updated', { sessionId: id, history: [] });
      return id;
    } catch (err) {
      this._logger.error('createSession failed', err);
      return '';
    }
  }

  async deleteSession(id: string): Promise<void> {
    try {
      const resp = await this._apiClient.deleteSession(id);
      if (!resp.ok) {
        this._logger.warn('deleteSession API returned', resp.status);
      }
    } catch (err) {
      this._logger.warn('deleteSession API failed', err);
    }
    // Update local state first
    this._sessions = this._sessions.filter(s => s.id !== id);
    delete this._histories[id];
    if (this._activeSessionId === id) {
      this._activeSessionId = this._sessions.length > 0 ? this._sessions[0].id : '';
    }
    // Notify UI to cleanup widgets, canvas, messages
    this._emit('session:deleted', { id });
    this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    if (this._activeSessionId) {
      this._emit('history:updated', { sessionId: this._activeSessionId, history: this.getHistory(this._activeSessionId) });
    }
    // Reload from backend to confirm
    await this.loadSessions();
  }

  async renameSession(id: string, name: string): Promise<void> {
    try {
      await this._apiClient.renameSession(id, name);
    } catch (err) {
      this._logger.warn('renameSession API failed', err);
    }
    const session = this._sessions.find(s => s.id === id);
    if (session) {
      session.name = name;
      this._emit('session:renamed', { id, name });
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    }
  }

  selectSession(id: string): void {
    if (this._activeSessionId !== id && this._sessions.some(s => s.id === id)) {
      this._activeSessionId = id;
      this._emit('session:selected', { id });
      // Load history for selected session
      this.loadHistory(id);
    }
  }

  addMessage(sessionId: string, msg: MessageData): void {
    if (!this._histories[sessionId]) {
      this._histories[sessionId] = [];
    }
    this._histories[sessionId].push(msg);
    const session = this._sessions.find(s => s.id === sessionId);
    if (session) {
      session.count = (session.count || 0) + 1;
      session.last_str = new Date().toISOString().substring(0, 10);
    }
    this._emit('history:updated', { sessionId, history: this.getHistory(sessionId) });
    this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
  }

  getHistory(sessionId: string): MessageData[] {
    return this._histories[sessionId] || [];
  }

  // ── API calls ──

  private async loadSessions(): Promise<void> {
    try {
      const resp = await this._apiClient.getSessions();
      const data = await resp.json() as Array<{ id: string; name: string; count: number; last_str: string }>;
      this._sessions = data;
      this._logger.info('loadSessions', `count=${data.length}`);
      if (data.length > 0) {
        this._activeSessionId = data[0].id;
        await this.loadHistory(this._activeSessionId);
      }
      this._loaded = true;
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    } catch (err) {
      this._logger.warn('loadSessions failed, using empty state', err);
      this._sessions = [];
      this._loaded = true;
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    }
  }

  private async loadHistory(sessionId: string): Promise<void> {
    try {
      const resp = await this._apiClient.getSessionMessages(sessionId);
      const json = await resp.json() as Record<string, unknown>;
      // API returns {messages: [...], widget_states: {...}}
      const messages = Array.isArray(json) ? json : (json.messages as MessageData[] || []);
      this._histories[sessionId] = messages;
      this._emit('history:updated', { sessionId, history: messages });
    } catch (err) {
      this._logger.warn('loadHistory failed', err);
      this._histories[sessionId] = [];
    }
  }

  private _emit(event: string, data: unknown): void {
    if (this._eventBus) {
      this._eventBus.emit(event, data);
    }
  }
}
