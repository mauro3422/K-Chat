import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { HealthOverviewPanel } from '../widgets/HealthOverviewPanel';
import { ApiClient } from '../api/ApiClient';

describe('HealthOverviewPanel', () => {
  let panelEl: HTMLElement;

  beforeEach(() => {
    document.getElementById('health-overview-panel')?.remove();
    panelEl = document.createElement('div');
    panelEl.id = 'health-overview-panel';
    document.body.appendChild(panelEl);
  });

  afterEach(() => {
    panelEl.remove();
    vi.restoreAllMocks();
  });

  it('renders a unified node health summary', () => {
    const apiClient = new ApiClient();
    const logger = { warn: vi.fn() } as unknown as { warn: (label: string, detail?: unknown) => void };
    const panel = new HealthOverviewPanel(apiClient, logger);
    panel.init();
    panel.render({
      status: 'ok',
      checks: { database: 'ok', llm_provider: 'configured' },
      coordination: {
        node_id: 'node-a',
        role: 'secondary',
        has_recent_primary: true,
        peer_count: 1,
        cluster: {
          peer_count: 1,
          reachable_peers: 1,
          unreachable_peers: 0,
          states: [{ node_id: 'peer-a', role: 'primary', healthy: true, memory_is_fresh: true }],
        },
      },
      memory: {
        queue_size: 2,
        freshness: { last_revision: 1234, last_sync: 1234, is_fresh: false },
      },
      sync: { memory_is_fresh: false, last_memory_revision: 1234, last_memory_sync: 1234 },
      failover: { required_misses: 2, miss_count: 0, last_action: 'idle', should_promote: false },
    });

    expect(panelEl.textContent).toContain('ok');
    expect(panelEl.textContent).toContain('node-a');
    expect(panelEl.textContent).toContain('1/1 peers');
    expect(panelEl.textContent).toContain('Memoria');
    expect(panelEl.textContent).toContain('Queue');
  });

  it('refreshes from /health', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      json: async () => ({
        status: 'ok',
        checks: { database: 'ok', llm_provider: 'configured' },
        coordination: { node_id: 'node-a', role: 'primary', has_recent_primary: true, peer_count: 0, cluster: { peer_count: 0, reachable_peers: 0, unreachable_peers: 0, states: [] } },
        memory: { queue_size: 0, freshness: { last_revision: 0, last_sync: 0, is_fresh: true } },
        sync: { memory_is_fresh: true, last_memory_revision: 0, last_memory_sync: 0 },
        failover: { required_misses: 2, miss_count: 0, last_action: 'idle', should_promote: false },
      }),
    });
    const apiClient = new ApiClient();
    const logger = { warn: vi.fn() } as unknown as { warn: (label: string, detail?: unknown) => void };
    const panel = new HealthOverviewPanel(apiClient, logger);
    panel.init();

    vi.stubGlobal('fetch', fetchMock);
    await panel.refresh();

    expect(panelEl.textContent).toContain('ok');
    expect(panelEl.textContent).toContain('node-a');
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
