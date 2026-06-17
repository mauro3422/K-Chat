/** Style overrides for a single layout cell */
export interface CellStyle {
  variant?: string;
  background?: string;
  border?: string;
  animation?: string;
  cssVars?: Record<string, string>;
}

/** A single cell/block in the layout grid */
export interface ICellLayout {
  id: string;
  component: string;
  label: string;
  gridArea: string;
  style: CellStyle;
  visible: boolean;
  order: number;
}

/** The grid layout engine — treats the UI as a grid of Lego blocks */
export interface ILayoutGrid {
  readonly cells: ICellLayout[];

  getCell(id: string): ICellLayout | undefined;
  moveCell(id: string, area: string): void;
  updateStyle(id: string, style: Partial<CellStyle>): void;
  addCell(cell: ICellLayout): void;
  removeCell(id: string): void;
  setVariant(id: string, variant: string): void;
  setVisibility(id: string, visible: boolean): void;
  reset(): void;

  /** Serialize current layout to CSS grid-template-areas string */
  toGridTemplate(): string;

  /** Persist / restore from localStorage */
  save(): void;
  load(): void;

  on(event: 'change', cb: (cells: ICellLayout[]) => void): void;
  off(event: 'change', cb: (cells: ICellLayout[]) => void): void;
}

/** Configuration for the Canvas Overlay */
export interface ICanvasOverlay {
  readonly canvas: HTMLCanvasElement | null;

  init(containerId?: string): void;
  startEffect(effect: 'rain' | 'particles' | 'snow' | 'fireworks' | 'none'): void;
  stopEffect(): void;
  setOpacity(opacity: number): void;
  setColor(color: string): void;

  /** Drawing mode: user draws blocks, AI reads them */
  startDrawMode(onDraw: (blocks: DrawBlock[]) => void): void;
  stopDrawMode(): void;
  clear(): void;

  resize(): void;
  destroy(): void;
}

/** A block drawn by the user on the canvas */
export interface DrawBlock {
  x: number;
  y: number;
  w: number;
  h: number;
  color: string;
  type: 'cell' | 'effect' | 'decoration';
}

/** CSS injection API — add/remove dynamic styles */
export interface ICSSInjector {
  inject(id: string, css: string): HTMLStyleElement;
  remove(id: string): void;
  has(id: string): boolean;
  clear(): void;
}

/** Audio system — plays sounds via EventBus events */
export interface IAudioBus {
  init(): void;
  play(sound: 'message' | 'error' | 'notification' | 'send' | 'connect'): void;
  setVolume(vol: number): void;
  setMuted(muted: boolean): void;
  destroy(): void;
}

/** Default cell definitions */
export const DEFAULT_CELLS: ICellLayout[] = [
  { id: 'sidebar',     component: 'SessionList',  label: 'Sidebar',  gridArea: 'sidebar', style: {}, visible: true, order: 0 },
  { id: 'chat',        component: 'ChatArea',     label: 'Chat',     gridArea: 'chat',    style: {}, visible: true, order: 1 },
  { id: 'canvas',      component: 'CanvasWorkspace', label: 'Canvas', gridArea: 'canvas', style: {}, visible: true, order: 2 },
  { id: 'debug',       component: 'DebugPanel',   label: 'Debug',    gridArea: 'debug',   style: {}, visible: false, order: 3 },
  { id: 'effects',     component: 'Effects',      label: 'Efectos',  gridArea: 'effects', style: {}, visible: true, order: 4 },
];

/** Default grid template */
export const DEFAULT_GRID_TEMPLATE = `
  "sidebar  chat     canvas"
  "sidebar  chat     canvas"
  "effects  toolbar  debug"
`;
