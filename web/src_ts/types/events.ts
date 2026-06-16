export type EventCallback<T = any> = (data: T) => void;

export interface IEventBus {
  on<T>(event: string, callback: EventCallback<T>): void;
  off<T>(event: string, callback: EventCallback<T>): void;
  emit<T>(event: string, data: T): void;
  removeAllListeners(event?: string): void;
}
