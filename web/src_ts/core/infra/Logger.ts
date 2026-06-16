import { IEventBus } from '../../types/events';
import { IDebugApi } from '../../types/api';
import { IDebugManager } from '../../types/debug';

export type LogLevel = 'D' | 'I' | 'W' | 'E';

export interface LogEntry {
  t: string;
  l: LogLevel;
  m: string;
  msg: string;
  d: unknown;
}

export interface ILogger {
  debug(msg: string, data?: unknown): void;
  info(msg: string, data?: unknown): void;
  warn(msg: string, data?: unknown): void;
  error(msg: string, data?: unknown): void;
}

export class Logger implements ILogger {
  private static _buffer: LogEntry[] = [];
  private static _flushTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(
    private name: string,
    private eventBus?: IEventBus,
    private apiClient?: IDebugApi,
    private debugManager?: IDebugManager,
  ) {}

  debug(msg: string, data?: unknown): void { this._log('D', msg, data); }
  info(msg: string, data?: unknown): void { this._log('I', msg, data); }
  warn(msg: string, data?: unknown): void { this._log('W', msg, data); }
  error(msg: string, data?: unknown): void { this._log('E', msg, data); }

  private _log(level: LogLevel, msg: string, data?: unknown): void {
    const entry: LogEntry = {
      t: new Date().toISOString(),
      l: level,
      m: this.name,
      msg: String(msg).substring(0, 2000),
      d: data ?? null,
    };

    Logger._buffer.push(entry);
    if (Logger._buffer.length > 500) Logger._buffer.shift();

    if (level === 'E') console.error(`[${this.name}]`, msg, data || '');
    else if (level === 'W') console.warn(`[${this.name}]`, msg, data || '');
    else console.log(`[${this.name}]`, msg, data || '');

    this.debugManager?.logUI(`[${level}][${this.name}]`, String(msg).substring(0, 120));

    if (level === 'E' && this.eventBus) {
      this.eventBus.emit('notification:show', {
        id: `log-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        type: 'error',
        message: `[${this.name}] ${msg}`,
      });
    }

    if (!Logger._flushTimer && this.apiClient) {
      Logger._flushTimer = setTimeout(() => {
        Logger._flushTimer = null;
        this._flush();
      }, 5000);
    }
  }

  private _flush(): void {
    if (Logger._buffer.length === 0 || !this.apiClient) return;
    const batch = Logger._buffer.splice(0, Math.min(Logger._buffer.length, 100));
    this.apiClient.sendClientLogs(batch).catch(() => {});
  }
}
