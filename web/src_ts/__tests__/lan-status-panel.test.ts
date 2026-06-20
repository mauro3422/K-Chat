import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { LanStatusPanel } from '../widgets/LanStatusPanel';
import { ApiClient } from '../api/ApiClient';

describe('LanStatusPanel', () => {
  let panelEl: HTMLElement;

  beforeEach(() => {
    document.getElementById('lan-status-panel')?.remove();
    panelEl = document.createElement('div');
    panelEl.id = 'lan-status-panel';
    document.body.appendChild(panelEl);
  });

  afterEach(() => {
    panelEl.remove();
    vi.restoreAllMocks();
  });

  it('renders a cluster summary and peer list', () => {
    const apiClient = new ApiClient();
    const logger = { warn: vi.fn() } as unknown as { warn: (label: string, detail?: unknown) => void };
    const panel = new LanStatusPanel(apiClient, logger);
    panel.init();
    panel.render({
      node: { node_id: 'node-a', role: 'secondary', memory_is_fresh: true },
      bridge: { peer_urls: ['http://peer-a:8000'] },
      cluster: {
        peer_count: 1,
        reachable_peers: 1,
        unreachable_peers: 0,
        states: [
          { node_id: 'peer-a', role: 'primary', healthy: true, memory_is_fresh: true, peer_url: 'http://peer-a:8000' },
        ],
      },
      sync: { memory_is_fresh: true },
    });

    expect(panelEl.textContent).toContain('Sync OK');
    expect(panelEl.textContent).toContain('1 peers');
    expect(panelEl.textContent).toContain('peer-a');
  });

  it('refreshes from api client', async () => {
    const syncStatus = vi.fn().mockResolvedValue({
        json: async () => ({
          node: { node_id: 'node-a', role: 'primary', memory_is_fresh: false },
          bridge: { peer_urls: [] },
          cluster: { peer_count: 0, reachable_peers: 0, unreachable_peers: 0, states: [] },
        }),
    });
    const apiClient = {
      syncStatus,
    } as unknown as ApiClient;
    const logger = { warn: vi.fn() } as unknown as { warn: (label: string, detail?: unknown) => void };
    const panel = new LanStatusPanel(apiClient, logger);
    panel.init();

    await panel.refresh();

    expect(panelEl.textContent).toContain('Sync pendiente');
    expect(panelEl.textContent).toContain('primary');
    expect(syncStatus).toHaveBeenCalledTimes(1);
  });
});
