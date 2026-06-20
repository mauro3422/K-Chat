import { ApiClient } from '../../api/ApiClient';
import { ILogger } from '../Logger';
import { getLogger } from '../infra/LoggerFactory';

type SystemLogEntry = {
  t?: string;
  ts?: string;
  l?: string;
  m?: string;
  msg?: string;
  d?: unknown;
  source?: string;
};

export class SystemLogPanel {
  private panelEl: HTMLElement | null = null;
  private debugContentEl: HTMLElement | null = null;
  private logsContentEl: HTMLElement | null = null;
  private debugTabBtn: HTMLElement | null = null;
  private logsTabBtn: HTMLElement | null = null;
  private logger: ILogger = getLogger('system-log-panel');
  private refreshQueued = false;
  private activeTab: 'debug' | 'logs' = 'debug';

  constructor(private readonly apiClient: ApiClient) {}

  init(): void {
    this.panelEl = document.getElementById('debug-panel');
    this.debugContentEl = document.getElementById('debug-content');
    this.logsContentEl = document.getElementById('system-log-content');
    this.debugTabBtn = document.getElementById('debug-tab-btn');
    this.logsTabBtn = document.getElementById('logs-tab-btn');

    this.debugTabBtn?.addEventListener('click', () => this.showTab('debug'));
    this.logsTabBtn?.addEventListener('click', () => this.showTab('logs'));
    this.showTab('debug');
  }

  private _lastEntriesJson = '';

  refresh(): void {
    if (this.activeTab !== 'logs' || !this.logsContentEl) return;
    if (this.refreshQueued) return;
    this.refreshQueued = true;
    this.apiClient.loadSystemLogs()
      .then((resp) => resp.json())
      .then((data) => {
        const entries = Array.isArray(data.entries) ? data.entries as SystemLogEntry[] : [];
        const json = JSON.stringify(entries);
        if (json === this._lastEntriesJson) return; // no changes, skip render
        this._lastEntriesJson = json;
        // Save scroll position
        const scrollTop = this.logsContentEl!.scrollTop;
        this.render(entries);
        // Restore scroll position
        this.logsContentEl!.scrollTop = scrollTop;
      })
      .catch((err: unknown) => {
        this.logger.warn('refresh failed', err);
        if (this.logsContentEl) {
          this.logsContentEl.textContent = 'Error cargando logs del sistema';
        }
      })
      .finally(() => {
        this.refreshQueued = false;
      });
  }

  private showTab(tab: 'debug' | 'logs'): void {
    this.activeTab = tab;
    if (this.debugContentEl) {
      this.debugContentEl.style.display = tab === 'debug' ? 'block' : 'none';
    }
    if (this.logsContentEl) {
      this.logsContentEl.style.display = tab === 'logs' ? 'block' : 'none';
    }
    this.debugTabBtn?.classList.toggle('active', tab === 'debug');
    this.logsTabBtn?.classList.toggle('active', tab === 'logs');
    if (tab === 'logs') {
      this.refresh();
    }
  }

  private render(entries: SystemLogEntry[]): void {
    if (!this.logsContentEl) return;
    const html: string[] = [];
    html.push('<div class="db-section" style="display:flex;justify-content:space-between;align-items:center">');
    html.push('<strong>Logs del sistema</strong>');
    html.push(`<button class="db-copy" data-copy-action="system-logs" style="font-size:11px;padding:2px 8px">📋 Copy All</button>`);
    html.push('</div>');
    html.push(`<div class="dbg-muted">Entradas: ${entries.length}</div>`);
    if (entries.length === 0) {
      html.push('<div class="dbg-muted">(sin logs todavía)</div>');
    } else {
      html.push('<div class="sl-container">');
      for (const entry of entries.slice(0, 200)) {
        const ts = this.formatTs(entry.t || entry.ts || '');
        const level = (entry.l || '').toUpperCase();
        const moduleName = entry.m || entry.source || 'system';
        const msg = this.escape(this.entryMessage(entry));
        html.push(
          `<div class="sl-item sl-${this.levelClass(level)}">` +
            `<span class="sl-ts">${ts}</span>` +
            `<span class="sl-tag">${this.escape(level || 'INFO')}</span>` +
            `<span class="sl-tag">${this.escape(moduleName)}</span>` +
            `<span class="sl-data">${msg}</span>` +
          `</div>`,
        );
      }
      html.push('</div>');
    }
    this.logsContentEl.innerHTML = html.join('');

    // Bind Copy All button
    const copyBtn = this.logsContentEl.querySelector('[data-copy-action="system-logs"]');
    if (copyBtn) {
      copyBtn.addEventListener('click', () => this.copyAll(copyBtn as HTMLElement));
    }
  }

  private copyAll(btn: HTMLElement): void {
    const entriesText = this.getAllText();
    navigator.clipboard.writeText(entriesText).then(() => {
      const orig = btn.textContent;
      btn.textContent = '✅ Copied!';
      setTimeout(() => { btn.textContent = orig; }, 1500);
    }).catch(() => {
      btn.textContent = '❌ Error';
    });
  }

  private getAllText(): string {
    if (!this.logsContentEl) return '';
    const lines: string[] = [];
    const items = this.logsContentEl.querySelectorAll('.sl-item');
    items.forEach((item) => {
      const ts = (item.querySelector('.sl-ts') as HTMLElement)?.textContent || '';
      const level = (item.querySelector('.sl-tag') as HTMLElement)?.textContent || '';
      const data = (item.querySelector('.sl-data') as HTMLElement)?.textContent || '';
      lines.push(`${ts} [${level}] ${data}`);
    });
    return lines.join('\n');
  }

  private formatTs(raw: string): string {
    if (!raw) return '--:--:--';
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) {
      return String(raw).slice(11, 23) || String(raw);
    }
    return date.toISOString().slice(11, 23);
  }

  private levelClass(level: string): string {
    if (level === 'ERROR') return 'error';
    if (level === 'WARN' || level === 'WARNING') return 'warning';
    if (level === 'DEBUG') return 'debug';
    return 'info';
  }

  private entryMessage(entry: SystemLogEntry): string {
    if (typeof entry.msg === 'string' && entry.msg.trim()) {
      return entry.msg;
    }
    if (typeof entry.d === 'string' && entry.d.trim()) {
      return entry.d;
    }
    if (entry.d && typeof entry.d === 'object') {
      try {
        return JSON.stringify(entry.d);
      } catch {
        return String(entry.d);
      }
    }
    return '';
  }

  private escape(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}
