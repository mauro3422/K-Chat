import { ApiClient } from '../api/ApiClient';
import { ILogger } from '../core/infra/Logger';

export interface LanPeerState {
  node_id?: string;
  role?: string;
  healthy?: boolean;
  memory_is_fresh?: boolean;
  peer_url?: string;
  source_url?: string;
}

export interface LanSyncStatus {
  ok?: boolean;
  node?: {
    node_id?: string;
    role?: string;
    healthy?: boolean;
    memory_is_fresh?: boolean;
  };
  bridge?: {
    base_url?: string;
    peer_urls?: string[];
  };
  cluster?: {
    peer_count?: number;
    reachable_peers?: number;
    unreachable_peers?: number;
    states?: LanPeerState[];
  };
  sync?: {
    is_primary?: boolean;
    has_recent_primary?: boolean;
    memory_is_fresh?: boolean;
    last_memory_revision?: number;
    last_memory_sync?: number;
  };
}

export class LanStatusPanel {
  private readonly apiClient: ApiClient;
  private readonly logger: ILogger;
  private panelEl: HTMLElement | null = null;

  constructor(apiClient: ApiClient, logger: ILogger) {
    this.apiClient = apiClient;
    this.logger = logger;
  }

  init(): void {
    this.panelEl = document.getElementById('lan-status-panel');
    if (!this.panelEl) {
      this.logger.warn('lan_status_panel_missing', 'lan-status-panel not found in DOM');
    }
  }

  async refresh(): Promise<void> {
    if (!this.panelEl) return;
    try {
      const resp = await this.apiClient.syncStatus();
      const raw = await resp.json() as LanSyncStatus & {
        health?: { sync?: LanSyncStatus['sync'] };
      };
      const data: LanSyncStatus = raw.health
        ? { ...raw, sync: raw.health.sync || raw.sync }
        : raw;
      this.render(data);
    } catch (err) {
      this.logger.warn('lan_status_refresh_failed', err);
      this.render(null);
    }
  }

  render(status: LanSyncStatus | null): void {
    if (!this.panelEl) return;

    if (!status) {
      this.panelEl.innerHTML = '<div class="lan-status-empty">Estado LAN no disponible</div>';
      return;
    }

    const cluster = status.cluster || {};
    const node = status.node || {};
    const peerCount = cluster.peer_count ?? (status.bridge?.peer_urls?.length || 0);
    const reachable = cluster.reachable_peers ?? 0;
    const unreachable = cluster.unreachable_peers ?? 0;
    const peerStates = cluster.states || [];
    const freshness = node.memory_is_fresh ?? status.sync?.memory_is_fresh ?? false;
    const role = node.role || (status.sync?.is_primary ? 'primary' : 'secondary');

    const peersHtml = peerStates.length
      ? `<ul class="lan-status-peers">${peerStates.map((peer) => {
          const healthy = peer.healthy ? 'ok' : 'warn';
          const freshnessLabel = peer.memory_is_fresh ? 'fresh' : 'stale';
          const label = `${peer.node_id || peer.source_url || 'peer'} · ${peer.role || 'secondary'}`;
          return `<li class="lan-status-peer lan-status-peer-${healthy}">
            <span class="lan-status-peer-label">${label}</span>
            <span class="lan-status-peer-meta">${freshnessLabel}</span>
          </li>`;
        }).join('')}</ul>`
      : '<div class="lan-status-empty">Sin peers visibles</div>';

    this.panelEl.innerHTML = `
      <div class="lan-status-summary">
        <span class="lan-status-pill lan-status-pill-${freshness ? 'ok' : 'warn'}">${freshness ? 'Sync OK' : 'Sync pendiente'}</span>
        <span class="lan-status-pill">${role}</span>
        <span class="lan-status-pill">${peerCount} peers</span>
      </div>
      <div class="lan-status-meta">
        <span>Reachable: ${reachable}</span>
        <span>Unreachable: ${unreachable}</span>
      </div>
      ${peersHtml}
    `;
  }
}
