import { ILayoutGrid, ICellLayout, CellStyle, DEFAULT_CELLS, DEFAULT_GRID_TEMPLATE } from '../../types/layout';
import { getLogger } from '../infra/LoggerFactory';
import { ILogger } from '../infra/Logger';

type ChangeCallback = (cells: ICellLayout[]) => void;

export class GridController implements ILayoutGrid {
  private _cells: ICellLayout[] = [];
  private logger: ILogger;
  private changeListeners: ChangeCallback[] = [];
  private storageKey = 'k-grid-v1-layout';
  private appEl: HTMLElement | null = null;

  constructor() {
    this.logger = getLogger('grid');
    this._cells = DEFAULT_CELLS.map(c => ({ ...c, style: { ...c.style } }));
  }

  get cells(): ICellLayout[] {
    return this._cells;
  }

  /** Initialize: load saved layout, apply to DOM */
  init(): void {
    this.appEl = document.getElementById('app');
    this.load();
    this.applyToDOM();
    this.logger.info('init', `cells=${this._cells.length}`);
  }

  getCell(id: string): ICellLayout | undefined {
    return this._cells.find(c => c.id === id);
  }

  moveCell(id: string, area: string): void {
    const cell = this._cells.find(c => c.id === id);
    if (!cell) return;
    cell.gridArea = area;
    this.logger.info('move', `id=${id} area=${area}`);
    this._notify();
    this.applyToDOM();
    this.save();
  }

  updateStyle(id: string, style: Partial<CellStyle>): void {
    const cell = this._cells.find(c => c.id === id);
    if (!cell) return;
    Object.assign(cell.style, style);
    this.logger.info(`updateStyle id=${id}`, style);
    this._notify();
    this.applyToDOM();
    this.save();
  }

  addCell(cell: ICellLayout): void {
    if (this._cells.find(c => c.id === cell.id)) return;
    this._cells.push(cell);
    this.logger.info('addCell', `id=${cell.id}`);
    this._notify();
    this.applyToDOM();
    this.save();
  }

  removeCell(id: string): void {
    const idx = this._cells.findIndex(c => c.id === id);
    if (idx < 0) return;
    this._cells.splice(idx, 1);
    this.logger.info('removeCell', `id=${id}`);
    this._notify();
    this.applyToDOM();
    this.save();
  }

  setVariant(id: string, variant: string): void {
    this.updateStyle(id, { variant });
  }

  setVisibility(id: string, visible: boolean): void {
    const cell = this._cells.find(c => c.id === id);
    if (!cell) return;
    cell.visible = visible;
    this.logger.info('setVisibility', `id=${id} visible=${visible}`);
    this._notify();
    this.applyToDOM();
    this.save();
  }

  reset(): void {
    this._cells = DEFAULT_CELLS.map(c => ({ ...c, style: { ...c.style } }));
    this.logger.info('reset');
    this._notify();
    this.applyToDOM();
    this.save();
  }

  toGridTemplate(): string {
    const visibleCells = this._cells.filter(c => c.visible);
    const cols: string[] = [];

    visibleCells.forEach(c => {
      cols.push(c.gridArea);
    });

    if (cols.length === 0) return '"chat"';
    return `"${cols.join(' ')}"`;
  }

  /** Apply current grid state to the DOM */
  private applyToDOM(): void {
    if (!this.appEl) {
      this.appEl = document.getElementById('app');
    }
    if (!this.appEl) return;

    const visibleCount = this._cells.filter(c => c.visible).length;
    this.appEl.classList.toggle('grid-layout', visibleCount > 1);

    this.appEl.style.gridTemplateAreas = this.toGridTemplate();

    this._cells.forEach(cell => {
      const el = this.appEl?.querySelector(`#${cell.id}`) as HTMLElement | null;
      if (!el) return;
      if (cell.style.variant) {
        el.dataset.variant = cell.style.variant;
      }
      if (cell.style.background) {
        el.style.background = cell.style.background;
      }
      if (cell.style.border) {
        el.style.border = cell.style.border;
      }
      if (cell.style.cssVars) {
        Object.entries(cell.style.cssVars).forEach(([key, val]) => {
          el.style.setProperty(key, val);
        });
      }
    });
  }

  private _notify(): void {
    this.changeListeners.forEach(cb => {
      try { cb([...this._cells]); } catch (e) { /* ignore */ }
    });
  }

  // ── Persistence ──

  save(): void {
    try {
      localStorage.setItem(this.storageKey, JSON.stringify(this._cells));
    } catch { /* localStorage full */ }
  }

  load(): void {
    try {
      const data = localStorage.getItem(this.storageKey);
      if (!data) return;
      const parsed = JSON.parse(data) as ICellLayout[];
      if (!Array.isArray(parsed)) return;
      const defaults = DEFAULT_CELLS.reduce((acc, c) => { acc[c.id] = c; return acc; }, {} as Record<string, ICellLayout>);
      this._cells = parsed.map(c => ({ ...defaults[c.id] || {}, ...c, style: { ...defaults[c.id]?.style || {}, ...c.style || {} } }));
    } catch { /* ignore */ }
  }

  // ── Events ──

  on(event: 'change', cb: (cells: ICellLayout[]) => void): void {
    if (event === 'change') this.changeListeners.push(cb);
  }

  off(event: 'change', cb: (cells: ICellLayout[]) => void): void {
    if (event === 'change') {
      this.changeListeners = this.changeListeners.filter(l => l !== cb);
    }
  }
}
