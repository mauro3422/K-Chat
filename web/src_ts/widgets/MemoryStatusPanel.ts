import { ApiClient } from '../api/ApiClient';
import { ILogger } from '../core/infra/Logger';

export interface MemoryDiagnostics {
  ok?: boolean;
  queue_size?: number;
  queue_path?: string;
  memory?: {
    revision?: number;
    sync?: number;
    is_fresh?: boolean;
  };
  compare_summary?: {
    severity?: string;
    actions?: string[];
    counts?: Record<string, number>;
    has_conflicts?: boolean;
  };
  compare?: {
    only_in_md?: unknown[];
    only_in_db?: unknown[];
    mismatched?: unknown[];
    rename_candidates?: unknown[];
  };
}

export class MemoryStatusPanel {
  private panelEl: HTMLElement | null = null;

  constructor(
    private readonly apiClient: ApiClient,
    private readonly logger: ILogger,
  ) {}

  init(): void {
    this.panelEl = document.getElementById('memory-status-panel');
    if (!this.panelEl) {
      this.logger.warn('memory_status_panel_missing', 'memory-status-panel not found in DOM');
    }
  }

  async refresh(): Promise<void> {
    if (!this.panelEl) return;
    try {
      const resp = await this.apiClient.memoryDiagnostics();
      const raw = await resp.json() as MemoryDiagnostics & { memory?: MemoryDiagnostics | MemoryDiagnostics['memory'] };
      // /api/diagnostics wraps the previous memory payload under `memory`.
      // Keep accepting the old flat shape so the component remains reusable.
      const nested = raw.memory;
      const data = nested && 'queue_size' in nested
        ? nested as MemoryDiagnostics
        : raw;
      this.render(data);
    } catch (err) {
      this.logger.warn('memory_status_refresh_failed', err);
      this.render(null);
    }
  }

  render(diagnostics: MemoryDiagnostics | null): void {
    if (!this.panelEl) return;

    if (!diagnostics) {
      this.panelEl.innerHTML = '<div class="memory-status-empty">Estado de memoria no disponible</div>';
      return;
    }

    const queueSize = diagnostics.queue_size ?? 0;
    const freshness = diagnostics.memory?.is_fresh ?? false;
    const severity = diagnostics.compare_summary?.severity || 'clean';
    const actions = diagnostics.compare_summary?.actions || [];
    const counts = diagnostics.compare_summary?.counts || {};
    const revision = diagnostics.memory?.revision ?? 0;
    const sync = diagnostics.memory?.sync ?? 0;

    this.panelEl.innerHTML = `
      <div class="memory-status-summary">
        <span class="memory-status-pill memory-status-pill-${freshness ? 'ok' : 'warn'}">${freshness ? 'Memoria fresca' : 'Memoria pendiente'}</span>
        <span class="memory-status-pill memory-status-pill-${severity === 'clean' ? 'ok' : severity === 'medium' ? 'warn' : 'danger'}">${severity}</span>
        <span class="memory-status-pill">${queueSize} en cola</span>
      </div>
      <div class="memory-status-meta">
        <span>Revision: ${this.formatTs(revision)}</span>
        <span>Sync: ${this.formatTs(sync)}</span>
      </div>
      <div class="memory-status-counts">
        <span>md: ${counts.only_in_md ?? 0}</span>
        <span>db: ${counts.only_in_db ?? 0}</span>
        <span>mismatch: ${counts.mismatched ?? 0}</span>
      </div>
      ${actions.length ? `<ul class="memory-status-actions">${actions.slice(0, 4).map((action) => `<li>${this.escape(String(action))}</li>`).join('')}</ul>` : '<div class="memory-status-empty">Sin acciones pendientes</div>'}
      <div class="memory-status-path">${this.escape(diagnostics.queue_path || '')}</div>
    `;
  }

  private formatTs(value: number): string {
    if (!value) return '--';
    return new Date(value * 1000).toLocaleTimeString([], { hour12: false });
  }

  private escape(value: string): string {
    return value
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }
}
