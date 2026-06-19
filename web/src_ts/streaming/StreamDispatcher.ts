import { StreamEventType } from '../types/streaming';
import { IStreamDispatcher, StreamHandler } from '../types/dispatcher';

/**
 * StreamDispatcher — distributes NDJSON stream events to registered handlers.
 * One dispatcher per stream session. Handlers receive (data: string, context).
 */
export class StreamDispatcher<TContext = unknown> implements IStreamDispatcher<TContext> {
  private handlers = new Map<string, Array<StreamHandler<TContext>>>();

  on(event: StreamEventType, callback: StreamHandler<TContext>): void {
    const list = this.handlers.get(event);
    if (list) {
      list.push(callback);
    } else {
      this.handlers.set(event, [callback]);
    }
  }

  off(event: StreamEventType, callback: StreamHandler<TContext>): void {
    const list = this.handlers.get(event);
    if (!list) return;
    const idx = list.indexOf(callback);
    if (idx >= 0) list.splice(idx, 1);
  }

  emit(event: StreamEventType, data: string, context: TContext): void {
    const list = this.handlers.get(event);
    if (!list) return;
    for (const cb of list) {
      try {
        cb(data, context);
      } catch (e) {
        console.error(`[StreamDispatcher] handler error for ${event}:`, e);
      }
    }
  }

  removeAll(): void {
    this.handlers.clear();
  }
}
