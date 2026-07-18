import { IEventBus, EventCallback } from '../../types/events';
import type { MessageData } from '../../types/messages';
import { ApiClient } from '../../api/ApiClient';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

export interface SessionSummary {
  id: string;
  name: string;
  count: number;
  last_str: string;
  node_id?: string;
  node_role?: string;
  node_platform?: string;
  cluster_name?: string;
  source_url?: string;
  source_mode?: string;
  is_favorite?: boolean;
}

export interface ISessionStore {
  readonly sessions: SessionSummary[];
  readonly activeSessionId: string;
  readonly activeHistory: MessageData[];

  init(eventBus: IEventBus, initialSessionId?: string): Promise<void>;
  createSession(name?: string): Promise<string>;
  deleteSession(id: string): Promise<void>;
  renameSession(id: string, name: string): Promise<void>;
  selectSession(id: string): Promise<void>;
  addMessage(sessionId: string, msg: MessageData): void;
  getHistory(sessionId: string): MessageData[];
}

export class SessionStore implements ISessionStore {
  private _sessions: SessionSummary[] = [];
  private _histories: Record<string, MessageData[]> = {};
  private _activeSessionId = '';
  private _initialSessionId = '';
  private _eventBus: IEventBus | null = null;
  private _apiClient: ApiClient;
  private _logger: ILogger;
  private _boundListeners: Array<{ event: string; cb: EventCallback<any> }> = [];
  private _loaded = false;
  private _selectGeneration = 0;

  constructor(apiClient: ApiClient) {
    this._apiClient = apiClient;
    this._logger = getLogger('session-store');
  }

  get sessions() { return this._sessions; }
  get activeSessionId() { return this._activeSessionId; }
  get activeHistory() { return this.getHistory(this._activeSessionId); }

  private _masterSessionBaseUrl(): string {
    const app = document.getElementById('app') as HTMLElement | null;
    const configured = app?.dataset.masterSessionBaseUrl?.replace(/\/+$/, '') || '';
    return configured || window.location.origin.replace(/\/+$/, '');
  }

  private _syncMasterLink(sessionId: string): void {
    const link = document.getElementById('master-session-link') as HTMLAnchorElement | null;
    if (!link) return;
    const baseUrl = this._masterSessionBaseUrl();
    if (!sessionId) {
      link.href = baseUrl || '/';
      return;
    }
    link.href = `${baseUrl}/go/${sessionId}`;
  }

  async init(eventBus: IEventBus, initialSessionId?: string): Promise<void> {
    this._eventBus = eventBus;
    this._initialSessionId = initialSessionId || '';

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

    const remoteRenameCb = (data: { id: string; name: string }) => {
      this.applySessionName(data.id, data.name);
    };
    eventBus.on<{ id: string; name: string }>('sse:session-renamed', remoteRenameCb);
    this._boundListeners.push({ event: 'sse:session-renamed', cb: remoteRenameCb as EventCallback<any> });

    const deleteCb = async (data: { sessionId: string }) => {
      await this.deleteSession(data.sessionId);
    };
    eventBus.on<{ sessionId: string }>('session:delete', deleteCb);
    this._boundListeners.push({ event: 'session:delete', cb: deleteCb as EventCallback<any> });

    // Load sessions from backend
    await this.loadSessions(this._initialSessionId);

    // Prefer initialSessionId from DOM (page refresh / direct URL) over data[0].id
    if (this._initialSessionId && this._sessions.some(s => s.id === this._initialSessionId)) {
      await this.selectSession(this._initialSessionId);
    }
    this._syncMasterLink(this._activeSessionId || this._initialSessionId || '');
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
      // Push new history entry so back button works after creating a session
      window.history.pushState({ sessionId: id }, '', `/go/${id}`);
      this._syncMasterLink(id);
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
      if (this._activeSessionId) {
        window.history.replaceState({ sessionId: this._activeSessionId }, '', `/go/${this._activeSessionId}`);
      } else {
        window.history.replaceState({}, '', '/');
      }
      this._syncMasterLink(this._activeSessionId);
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
    this.applySessionName(id, name);
  }

  private applySessionName(id: string, name: string): void {
    const session = this._sessions.find(s => s.id === id);
    if (session) {
      session.name = name;
      this._emit('session:renamed', { id, name });
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    }
  }

  async selectSession(id: string): Promise<void> {
    const session = this._sessions.find(s => s.id === id);
    if (!session) return;

    const sourceUrl = (session.source_url || '').replace(/\/+$/, '');
    const currentOrigin = window.location.origin.replace(/\/+$/, '');
    // Redirect to origin node if the session belongs to another PC.
    // Memory sync replicates metadata (name, dates) but NOT messages,
    // so we need to redirect to load the actual chat content.
    if (sourceUrl && sourceUrl !== currentOrigin) {
      window.location.assign(`${sourceUrl}/go/${id}`);
      return;
    }

    const canonicalPath = `/go/${id}`;
    const needsUrlSync = window.location.pathname !== canonicalPath;

    if (this._activeSessionId !== id) {
      this._activeSessionId = id;
      this._selectGeneration++;
      const gen = this._selectGeneration;
      // Load history for selected session
      await this.loadHistory(id);
      if (gen !== this._selectGeneration) return;
      this._emit('session:selected', { id });
      if (needsUrlSync) {
        window.history.replaceState({ sessionId: id }, '', canonicalPath);
      }
    } else if (needsUrlSync) {
      // Normalize direct /sessions/:id entries to the master URL.
      window.history.replaceState({ sessionId: id }, '', canonicalPath);
    }
    this._syncMasterLink(id);
  }

  addMessage(sessionId: string, msg: MessageData): void {
    if (!this._histories[sessionId]) {
      this._histories[sessionId] = [];
    }
    this._histories[sessionId].push(msg);
    const session = this._sessions.find(s => s.id === sessionId);
    if (session) {
      if (msg.role === 'user') {
        session.count = (session.count || 0) + 1;
      }
      session.last_str = new Date().toISOString().substring(0, 10);
    }
    this._emit('history:updated', { sessionId, history: this.getHistory(sessionId) });
    this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
  }

  getHistory(sessionId: string): MessageData[] {
    return this._histories[sessionId] || [];
  }

  /** Check if a session belongs to this node (same origin). */
  private _isLocalSession(session: SessionSummary): boolean {
    const sourceUrl = (session.source_url || '').replace(/\/+$/, '');
    const currentOrigin = window.location.origin.replace(/\/+$/, '');
    return !sourceUrl || sourceUrl === currentOrigin;
  }

  // ── API calls ──

  private async loadSessions(preferredSessionId: string = ''): Promise<void> {
    try {
      const resp = await this._apiClient.getSessions();
      const data = await resp.json() as SessionSummary[];
      this._sessions = data;
      this._logger.info('loadSessions', `count=${data.length}`);
      const preferred = preferredSessionId && data.some(s => s.id === preferredSessionId)
        ? preferredSessionId
        : '';
      if (preferred) {
        this._activeSessionId = preferred;
        const selected = this._sessions.find(s => s.id === preferred);
        // Only load history if session belongs to this node
        if (!selected || this._isLocalSession(selected)) {
          await this.loadHistory(this._activeSessionId);
        }
      } else if (data.length > 0) {
        this._activeSessionId = data[0].id;
        const selected = this._sessions[0];
        if (!selected || this._isLocalSession(selected)) {
          await this.loadHistory(this._activeSessionId);
        }
      }
      this._loaded = true;
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
      this._syncMasterLink(this._activeSessionId);
    } catch (err) {
      this._logger.warn('loadSessions failed, using empty state', err);
      this._sessions = [];
      this._loaded = true;
      this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
      this._syncMasterLink(this._activeSessionId);
    }
  }

  async loadHistory(sessionId: string): Promise<void> {
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
