import { IEventBus } from '../../types/events';
import { INotification } from './NotificationService';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

const COLORS: Record<string, { bg: string; text: string }> = {
  error: { bg: '#f85149', text: '#fff' },
  warning: { bg: '#f39c12', text: '#fff' },
  info: { bg: '#58a6ff', text: '#fff' },
  success: { bg: '#3fb950', text: '#fff' },
};

export class ToastUI {
  private eventBus: IEventBus;
  private logger: ILogger = getLogger('toast');
  private currentEl: HTMLElement | null = null;
  private fadeTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(eventBus: IEventBus) {
    this.eventBus = eventBus;
  }

  init(): void {
    this.eventBus.on<INotification>('notification:show', (n) => this.handleShow(n));
    this.eventBus.on<{ id: string }>('notification:dismiss', (d) => this.handleDismiss(d.id));
  }

  private handleShow(notification: INotification): void {
    if (this.fadeTimer) {
      clearTimeout(this.fadeTimer);
      this.fadeTimer = null;
    }

    if (this.currentEl) {
      this.removeCurrentElement();
    }

    this.logger.info('toast_shown', `type=${notification.type} msg="${notification.message.substring(0, 80)}"`);

    requestAnimationFrame(() => {
      const color = COLORS[notification.type] || COLORS.info;
      const toast = document.createElement('div');
      toast.id = 'kairos-toast';
      toast.style.cssText = [
        'position:fixed',
        'bottom:20px',
        'right:20px',
        `background:${color.bg}`,
        `color:${color.text}`,
        'padding:12px 20px',
        'border-radius:8px',
        'z-index:9999',
        'font-size:14px',
        'box-shadow:0 4px 12px rgba(0,0,0,0.3)',
        'cursor:pointer',
        'opacity:0',
        'transition:opacity 0.2s ease-in-out',
      ].join(';');
      toast.textContent = notification.message;
      toast.onclick = () => {
        this.eventBus.emit('notification:dismiss', { id: notification.id });
      };

      document.body.appendChild(toast);
      this.currentEl = toast;

      requestAnimationFrame(() => {
        toast.style.opacity = '1';
      });
    });
  }

  private handleDismiss(id: string): void {
    if (!this.currentEl) return;

    this.currentEl.style.opacity = '0';
    this.logger.info('toast_dismissed', `id=${id}`);
    this.fadeTimer = setTimeout(() => {
      this.removeCurrentElement();
    }, 200);
  }

  private removeCurrentElement(): void {
    if (this.currentEl && this.currentEl.parentNode) {
      this.currentEl.parentNode.removeChild(this.currentEl);
    }
    this.currentEl = null;
  }
}
