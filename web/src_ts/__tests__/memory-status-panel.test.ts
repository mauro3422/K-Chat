import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { MemoryStatusPanel } from '../widgets/MemoryStatusPanel';
import { ApiClient } from '../api/ApiClient';

describe('MemoryStatusPanel', () => {
  let panelEl: HTMLElement;

  beforeEach(() => {
    document.getElementById('memory-status-panel')?.remove();
    panelEl = document.createElement('div');
    panelEl.id = 'memory-status-panel';
    document.body.appendChild(panelEl);
  });

  afterEach(() => {
    panelEl.remove();
    vi.restoreAllMocks();
  });

  it('renders memory sync summary and actions', () => {
    const apiClient = new ApiClient();
    const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() };
    const panel = new MemoryStatusPanel(apiClient, logger);
    panel.init();
    panel.render({
      queue_size: 2,
      queue_path: 'C:/tmp/queue.json',
      memory: { revision: 1234, sync: 1234, is_fresh: false },
      compare_summary: {
        severity: 'high',
        actions: ['revisar valores desalineados entre MEMORY.md y memory.db', 'eliminar entradas huérfanas de memory.db'],
        counts: { only_in_md: 1, only_in_db: 2, mismatched: 3 },
        has_conflicts: true,
      },
    });

    expect(panelEl.textContent).toContain('Memoria pendiente');
    expect(panelEl.textContent).toContain('high');
    expect(panelEl.textContent).toContain('2 en cola');
    expect(panelEl.textContent).toContain('revisar valores desalineados');
  });

  it('refreshes from api client', async () => {
    const memoryDiagnostics = vi.fn().mockResolvedValue({
      json: async () => ({
        memory: {
          queue_size: 0,
          queue_path: '',
          memory: { revision: 0, sync: 0, is_fresh: true },
          compare_summary: { severity: 'clean', actions: [], counts: {}, has_conflicts: false },
        },
      }),
    });
    const apiClient = {
      memoryDiagnostics,
    } as unknown as ApiClient;
    const logger = { debug: vi.fn(), info: vi.fn(), warn: vi.fn(), error: vi.fn() };
    const panel = new MemoryStatusPanel(apiClient, logger);
    panel.init();

    await panel.refresh();

    expect(panelEl.textContent).toContain('Memoria fresca');
    expect(panelEl.textContent).toContain('clean');
    expect(memoryDiagnostics).toHaveBeenCalledTimes(1);
  });
});
