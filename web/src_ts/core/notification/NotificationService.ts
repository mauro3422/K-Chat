import { IEventBus } from '../../types/events';

export type NotificationType = 'info' | 'success' | 'warning' | 'error';

export interface INotification {
  id: string;
  type: NotificationType;
  message: string;
  duration?: number;
  action?: { label: string; onClick: () => void };
}

export interface INotificationService {
  readonly current: INotification | null;
  show(type: NotificationType, message: string, duration?: number): string;
  dismiss(id: string): void;
  dismissAll(): void;
}

const DEFAULT_DURATIONS: Record<NotificationType, number> = {
  info: 6000,
  success: 6000,
  warning: 8000,
  error: 8000,
};

export class NotificationService implements INotificationService {
  private eventBus: IEventBus;
  private _current: INotification | null = null;
  private timerId: ReturnType<typeof setTimeout> | null = null;

  constructor(eventBus: IEventBus) {
    this.eventBus = eventBus;
  }

  get current(): INotification | null {
    return this._current;
  }

  show(type: NotificationType, message: string, duration?: number): string {
    if (this._current) {
      this.dismiss(this._current.id);
    }

    const id = this.generateId();
    const effectiveDuration = duration ?? DEFAULT_DURATIONS[type];

    const notification: INotification = {
      id,
      type,
      message,
      duration: effectiveDuration,
    };

    this._current = notification;
    this.eventBus.emit('notification:show', notification);

    if (effectiveDuration > 0) {
      this.timerId = setTimeout(() => {
        this.dismiss(id);
      }, effectiveDuration);
    }

    return id;
  }

  dismiss(id: string): void {
    if (this._current && this._current.id === id) {
      if (this.timerId) {
        clearTimeout(this.timerId);
        this.timerId = null;
      }
      this._current = null;
      this.eventBus.emit('notification:dismiss', { id });
    }
  }

  dismissAll(): void {
    if (this._current) {
      const id = this._current.id;
      if (this.timerId) {
        clearTimeout(this.timerId);
        this.timerId = null;
      }
      this._current = null;
      this.eventBus.emit('notification:dismiss', { id });
    }
  }

  private generateId(): string {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
  }
}
