import { IEventBus, EventCallback } from '../../types/events';
import { getLogger } from './LoggerFactory';
import { ILogger } from './Logger';

export class TypedEventBus implements IEventBus {
  private logger: ILogger = getLogger('event-bus');
  private listeners: Map<string, EventCallback[]> = new Map();
  private static readonly MAX_LISTENERS = 50;
  private static _logDepth = 0;

  on<T>(event: string, callback: EventCallback<T>): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    const list = this.listeners.get(event)!;
    if (list.length >= TypedEventBus.MAX_LISTENERS) {
      console.warn(`[EventBus] Max listeners (${TypedEventBus.MAX_LISTENERS}) for "${event}" — possible leak`);
      return;
    }
    list.push(callback);
    this._logDebug('on', event);
  }

  off<T>(event: string, callback: EventCallback<T>): void {
    const list = this.listeners.get(event);
    if (!list) return;
    this.listeners.set(
      event,
      list.filter((cb) => cb !== callback)
    );
    this._logDebug('off', event);
  }

  emit<T>(event: string, data: T): void {
    this._logDebug('emit', event);
    const list = this.listeners.get(event);
    if (!list) return;
    for (const callback of list) {
      try {
        Promise.resolve(callback(data)).catch((err) => {
          console.error(`Unhandled rejection in event listener for ${event}:`, err);
        });
      } catch (error) {
        console.error(`Error in event listener for ${event}:`, error);
      }
    }
  }

  removeAllListeners(event?: string): void {
    if (event) {
      this.listeners.delete(event);
    } else {
      this.listeners.clear();
    }
    this._logDebug('remove_all', event || '*');
  }

  private _logDebug(action: string, event: string): void {
    if (TypedEventBus._logDepth > 0) return;
    TypedEventBus._logDepth++;
    try {
      this.logger.debug(`${action} "${event}"`);
    } finally {
      TypedEventBus._logDepth--;
    }
  }
}
