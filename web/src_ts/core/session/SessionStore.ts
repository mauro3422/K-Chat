import { IEventBus, EventCallback } from '../../types/events';
import { MessageData } from '../../rendering/MessageView';
import { randomWidget } from '../../widgets/templates';

export interface ISessionStore {
  readonly sessions: Array<{ id: string; name: string; count: number; last_str: string }>;
  readonly activeSessionId: string;
  readonly activeHistory: MessageData[];

  init(eventBus: IEventBus): void;
  createSession(name?: string): string;
  deleteSession(id: string): void;
  renameSession(id: string, name: string): void;
  selectSession(id: string): void;
  addMessage(sessionId: string, msg: MessageData): void;
  getHistory(sessionId: string): MessageData[];
}

export class SessionStore implements ISessionStore {
  private _sessions: Array<{ id: string; name: string; count: number; last_str: string }>;
  private _histories: Record<string, MessageData[]>;
  private _activeSessionId: string;
  private _eventBus: IEventBus | null = null;
  private _boundListeners: Array<{ event: string; cb: EventCallback<any> }> = [];

  constructor() {
    this._sessions = [
      { id: 'sess-1', name: 'Conversación de Prueba', count: 2, last_str: '2026-06-16' },
      { id: 'sess-2', name: 'Ideas de Desarrollo', count: 1, last_str: '2026-06-15' },
      { id: 'sess-3', name: 'Widgets & UI', count: 3, last_str: '2026-06-16' },
      { id: 'tele_12345', name: 'Telegram Bridge', count: 1, last_str: '2026-06-14' },
    ];

    this._histories = {
      'sess-1': [
        { role: 'user', content: '¿Qué es este prototipo?', ts: '2026-06-16T12:00:00Z' },
        {
          role: 'assistant',
          content: '¡Hola! Este es el prototipo TypeScript de K-Chat usando arquitectura de bloques Lego. Todo está desacoplado vía EventBus e inyección de dependencias.',
          reasoning: 'El usuario pregunta por el sistema. Explicar la arquitectura Lego.',
          ts: '2026-06-16T12:00:05Z',
          matched_tools: [{ tool_name: 'read_file', status: 'ok', turn: 1 }],
        },
      ],
      'sess-2': [
        { role: 'assistant', content: 'Aquí puedes simular ideas y probar la UI de K-Chat.', ts: '2026-06-15T10:00:00Z' },
      ],
      'sess-3': [
        { role: 'user', content: 'Muéstrame un widget', ts: '2026-06-16T14:00:00Z' },
        {
          role: 'assistant',
          content: `Aquí tienes un widget de reloj:\n\n\`\`\`html-widget clock\n${randomWidget()}\n\`\`\`\n\nFunciona dentro de un iframe sandboxed.`,
          ts: '2026-06-16T14:00:05Z',
          matched_tools: [{ tool_name: 'widget_create', status: 'ok', turn: 1 }],
        },
      ],
      'tele_12345': [
        {
          role: 'assistant',
          content: 'Conexión con Telegram activa. Eventos canalizados vía EventBus.',
          ts: '2026-06-14T09:00:00Z',
        },
      ],
    };

    this._activeSessionId = 'sess-1';
  }

  get sessions() { return this._sessions; }
  get activeSessionId() { return this._activeSessionId; }
  get activeHistory() { return this.getHistory(this._activeSessionId); }

  init(eventBus: IEventBus): void {
    this._eventBus = eventBus;

    const selectCb = (data: { sessionId: string }) => {
      this.selectSession(data.sessionId);
    };
    eventBus.on<{ sessionId: string }>('session:select', selectCb);
    this._boundListeners.push({ event: 'session:select', cb: selectCb });

    const renameCb = (data: { sessionId: string; name: string }) => {
      this.renameSession(data.sessionId, data.name);
    };
    eventBus.on<{ sessionId: string; name: string }>('session:rename', renameCb);
    this._boundListeners.push({ event: 'session:rename', cb: renameCb });

    const deleteCb = (data: { sessionId: string }) => {
      this.deleteSession(data.sessionId);
    };
    eventBus.on<{ sessionId: string }>('session:delete', deleteCb);
    this._boundListeners.push({ event: 'session:delete', cb: deleteCb });
  }

  dispose(): void {
    if (this._eventBus) {
      this._boundListeners.forEach(({ event, cb }) => this._eventBus!.off(event, cb));
    }
    this._boundListeners = [];
  }

  createSession(name?: string): string {
    const id = 'sess-' + Date.now();
    this._sessions.unshift({
      id,
      name: name || 'Nueva Conversación',
      count: 0,
      last_str: new Date().toISOString().substring(0, 10),
    });
    this._histories[id] = [];
    this._activeSessionId = id;
    this._emit('session:created', { id });
    this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    this._emit('history:updated', { sessionId: id, history: [] });
    return id;
  }

  deleteSession(id: string): void {
    this._sessions = this._sessions.filter(s => s.id !== id);
    delete this._histories[id];
    if (this._activeSessionId === id) {
      this._activeSessionId = this._sessions.length > 0 ? this._sessions[0].id : '';
    }
    this._emit('session:deleted', { id });
    this._emit('sessions:updated', { sessions: this._sessions, activeId: this._activeSessionId });
    // Emit history:updated so UI reloads the new active session's messages
    if (this._activeSessionId) {
      this._emit('history:updated', { sessionId: this._activeSessionId, history: this.getHistory(this._activeSessionId) });
    }
  }

  renameSession(id: string, name: string): void {
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
      this._emit('history:updated', { sessionId: id, history: this.getHistory(id) });
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

  private _emit(event: string, data: unknown): void {
    if (this._eventBus) {
      this._eventBus.emit(event, data);
    }
  }
}
