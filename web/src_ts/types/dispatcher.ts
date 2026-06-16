import { StreamEventType } from './streaming';

export type StreamHandler<TContext> = (data: string, context: TContext) => void;

export interface IStreamDispatcher<TContext = unknown> {
  on(event: StreamEventType, callback: StreamHandler<TContext>): void;
  off(event: StreamEventType, callback: StreamHandler<TContext>): void;
  emit(event: StreamEventType, data: string, context: TContext): void;
  removeAll(): void;
}
