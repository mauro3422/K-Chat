import { ApiClient } from '../api/ApiClient';
import { ILogger } from '../core/infra/Logger';

export interface HealthOverview {
  status?: string;
  checks?: Record<string, string>;
  coordination?: {
    node_id?: string;
    role?: string;
    has_recent_primary?: boolean;
    peer_count?: number;
    cluster?: {
      peer_count?: number;
      reachable_peers?: number;
      unreachable_peers?: number;
      states?: Array<{
        node_id?: string;
        role?: string;
        healthy?: boolean;
        memory_is_fresh?: boolean;
      }>;
    };
  };
  memory?: {
    queue_size?: number;
    freshness?: {
      last_revision?: number;
      last_sync?: number;
      is_fresh?: boolean;
    };
  };
  sync?: {
    role?: string;
    is_primary?: boolean;
    has_recent_primary?: boolean;
    memory_is_fresh?: boolean;
    last_memory_revision?: number;
    last_memory_sync?: number;
  };
  failover?: {
    required_misses?: number;
    miss_count?: number;
    last_action?: string;
    last_reason?: string;
    should_promote?: boolean;
  };
}

export class HealthOverviewPanel {
  private panelEl: HTMLElement | null = null;

  constructor(
    private readonly apiClient: ApiClient,
    private readonly logger: ILogger,
  ) {}

  init(): void {
    this.panelEl = document.getElementById('health-overview-panel');
    if (!this.panelEl) {
      this.logger.warn('health_overview_panel_missing', 'health-overview-panel not found in DOM');
    }
  }

  async refresh(): Promise<void> {
    if (!this.panelEl) return;
    try {
      const resp = await this.apiClient.health();
      const data = await resp.json() as HealthOverview;
      this.render(data);
    } catch (err) {
      this.logger.warn('health_overview_refresh_failed', err);
      this.render(null);
    }
  }

  render(health: HealthOverview | null): void {
    if (!this.panelEl) return;
    if (!health) {
      this.panelEl.innerHTML = '<div class="health-overview-empty">Salud total no disponible</div>';
      return;
    }

    const status = health.status || 'unknown';
    const statusLabel = this.escape(status);
    const checks = health.checks || {};
    const coord = health.coordination || {};
    const cluster = coord.cluster || {};
    const sync = health.sync || {};
    const memory = health.memory || {};
    const failover = health.failover || {};
    const healthyPeers = cluster.reachable_peers ?? 0;
    const totalPeers = cluster.peer_count ?? coord.peer_count ?? 0;
    const memoryFresh = memory.freshness?.is_fresh ?? sync.memory_is_fresh ?? false;

    this.panelEl.innerHTML = `
      <div class="health-overview-summary">
        <span class="health-overview-pill health-overview-pill-${status === 'ok' ? 'ok' : 'warn'}">${statusLabel}</span>
        <span class="health-overview-pill">${this.escape(coord.node_id || 'node')}</span>
        <span class="health-overview-pill">${this.escape(coord.role || sync.role || 'secondary')}</span>
        <span class="health-overview-pill">${healthyPeers}/${totalPeers} peers</span>
      </div>
      <div class="health-overview-grid">
        <div><strong>DB</strong><span>${this.escape(checks.database || 'n/a')}</span></div>
        <div><strong>LLM</strong><span>${this.escape(checks.llm_provider || 'n/a')}</span></div>
        <div><strong>Memoria</strong><span>${memoryFresh ? 'fresca' : 'pendiente'}</span></div>
        <div><strong>Queue</strong><span>${memory.queue_size ?? 0}</span></div>
        <div><strong>Failover</strong><span>${this.escape(failover.last_action || 'idle')}</span></div>
        <div><strong>Promote</strong><span>${failover.should_promote ? 'sí' : 'no'}</span></div>
      </div>
      <div class="health-overview-meta">
        <span>Primario reciente: ${coord.has_recent_primary ? 'sí' : 'no'}</span>
        <span>Misses: ${failover.miss_count ?? 0}/${failover.required_misses ?? 0}</span>
        <span>Revisado: ${this.formatTs(memory.freshness?.last_revision || sync.last_memory_revision || 0)}</span>
      </div>
      <div class="health-overview-note">${this.escape(failover.last_reason || '')}</div>
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
