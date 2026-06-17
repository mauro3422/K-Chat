import { IEventBus, EventCallback } from '../../types/events';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

interface HistoryEntry {
  id: string;
  type: string;
  message: string;
  timestamp: number;
}

export interface INotificationBell {
  init(): void;
}

const MAX_HISTORY = 50;
const BADGE_DISMISS_MS = 8000;

export class NotificationBell implements INotificationBell {
  private eventBus: IEventBus;
  private logger: ILogger = getLogger('notification');
  private history: HistoryEntry[] = [];
  private badgeCount = 0;
  private bellEl: HTMLElement | null = null;
  private badgeEl: HTMLElement | null = null;
  private dropdownEl: HTMLElement | null = null;
  private listEl: HTMLElement | null = null;
  private dismissTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private _boundListeners: Array<{ event: string; cb: EventCallback<any> }> = [];
  private _bellCb: ((e: MouseEvent) => void) | null = null;
  private _clickCb: ((e: MouseEvent) => void) | null = null;
  private _clearCb: (() => void) | null = null;

  constructor(eventBus: IEventBus) {
    this.eventBus = eventBus;
  }

  init(): void {
    this.bellEl = document.getElementById('notification-bell');
    this.badgeEl = document.getElementById('notification-badge');
    if (!this.bellEl || !this.badgeEl) return;
    this.createDropdown();
    this.attachEvents();
  }

  private createDropdown(): void {
    this.dropdownEl = document.createElement('div');
    this.dropdownEl.id = 'notif-dropdown';
    this.dropdownEl.className = 'notif-dropdown';
    this.dropdownEl.innerHTML = `
      <div class="notif-header">Notificaciones del Sistema</div>
      <div id="notif-list" class="notif-list"></div>
      <div class="notif-footer">
        <button id="notif-clear" class="notif-clear-btn">🗑 Limpiar</button>
      </div>
    `;
    this.listEl = this.dropdownEl.querySelector('#notif-list');
    this._clearCb = () => this.clearAll();
    this.dropdownEl.querySelector('#notif-clear')?.addEventListener('click', this._clearCb);
    this.bellEl!.parentNode?.insertBefore(this.dropdownEl, this.bellEl!.nextSibling);
  }

  private attachEvents(): void {
    this._bellCb = (e: MouseEvent) => {
      e.stopPropagation();
      this.toggleDropdown();
    };
    this.bellEl!.addEventListener('click', this._bellCb);

    this._clickCb = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        this.dropdownEl &&
        !this.dropdownEl.contains(target) &&
        target !== this.bellEl &&
        !this.bellEl!.contains(target)
      ) {
        this.closeDropdown();
      }
    };
    document.addEventListener('click', this._clickCb);

    const showCb = (data: any) => {
      this.addEntry(data.type, data.message, data.id);
    };
    this.eventBus.on<any>('notification:show', showCb);
    this._boundListeners.push({ event: 'notification:show', cb: showCb });

    const dismissCb = (data: { id: string }) => {
      this.removeBadge(data.id);
    };
    this.eventBus.on<{ id: string }>('notification:dismiss', dismissCb);
    this._boundListeners.push({ event: 'notification:dismiss', cb: dismissCb });

    const rlStartedCb = () => {
      this.addEntry('warning', '⏳ Rate limit activado');
    };
    this.eventBus.on('rate-limit:started', rlStartedCb);
    this._boundListeners.push({ event: 'rate-limit:started', cb: rlStartedCb });

    const rlExpiredCb = () => {
      this.addEntry('info', '✅ Rate limit expirado');
    };
    this.eventBus.on('rate-limit:expired', rlExpiredCb);
    this._boundListeners.push({ event: 'rate-limit:expired', cb: rlExpiredCb });
  }

  dispose(): void {
    this._boundListeners.forEach(({ event, cb }) => this.eventBus?.off(event, cb));
    this._boundListeners = [];
    if (this._bellCb) this.bellEl?.removeEventListener('click', this._bellCb);
    if (this._clickCb) document.removeEventListener('click', this._clickCb);
    if (this._clearCb) this.dropdownEl?.querySelector('#notif-clear')?.removeEventListener('click', this._clearCb);
    this.dismissTimers.forEach(t => clearTimeout(t));
    this.dismissTimers.clear();
  }

  private addEntry(type: string, message: string, id?: string): void {
    const entryId = id || `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    const entry: HistoryEntry = { id: entryId, type, message, timestamp: Date.now() };
    this.history.unshift(entry);
    if (this.history.length > MAX_HISTORY) this.history.pop();

    this.badgeCount++;
    this.updateBadge();
    this.logger.info('new_entry', `type=${type} msg="${message.substring(0, 60)}"`);

    const timer = setTimeout(() => {
      this.badgeCount = Math.max(0, this.badgeCount - 1);
      this.updateBadge();
      this.dismissTimers.delete(entryId);
      this.logger.info('dismiss_timer', `id=${entryId}`);
    }, BADGE_DISMISS_MS);
    this.dismissTimers.set(entryId, timer);

    if (this.dropdownEl?.classList.contains('open')) {
      this.renderList();
    }
  }

  private removeBadge(id: string): void {
    const timer = this.dismissTimers.get(id);
    if (timer) {
      clearTimeout(timer);
      this.dismissTimers.delete(id);
    }
    this.badgeCount = Math.max(0, this.badgeCount - 1);
    this.updateBadge();
    this.logger.info('remove_badge', `id=${id}`);
  }

  private updateBadge(): void {
    if (!this.badgeEl) return;
    if (this.badgeCount > 0) {
      this.badgeEl.style.display = 'flex';
      this.badgeEl.textContent = String(this.badgeCount > 99 ? '99+' : this.badgeCount);
    } else {
      this.badgeEl.style.display = 'none';
    }
  }

  private toggleDropdown(): void {
    if (!this.dropdownEl) return;
    const isOpen = this.dropdownEl.classList.toggle('open');
    this.logger.info('toggle', isOpen ? 'open' : 'close');
    if (isOpen) this.renderList();
  }

  private closeDropdown(): void {
    this.dropdownEl?.classList.remove('open');
  }

  private renderList(): void {
    if (!this.listEl) return;
    if (this.history.length === 0) {
      this.listEl.innerHTML = '<div class="notif-empty">No hay notificaciones</div>';
      return;
    }
    let html = '';
    for (const entry of this.history) {
      const time = new Date(entry.timestamp).toLocaleTimeString('es-ES', {
        hour: '2-digit', minute: '2-digit', second: '2-digit',
      });
      html += `<div class="notif-item type-${entry.type}">
        <span class="notif-time">${time}</span>
        <span class="notif-msg">${this.esc(entry.message)}</span>
      </div>`;
    }
    this.listEl.innerHTML = html;
  }

  private clearAll(): void {
    this.history = [];
    this.badgeCount = 0;
    this.updateBadge();
    for (const t of this.dismissTimers.values()) clearTimeout(t);
    this.dismissTimers.clear();
    this.renderList();
    this.closeDropdown();
    this.logger.info('clear_all');
  }

  private esc(s: string): string {
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }
}
