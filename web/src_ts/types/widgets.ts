export interface IWidgetRegistry {
  nextIndex(): string;
  getIndex(): number;
  register(code: string, key?: string): string;
  getCode(id: string): string | undefined;
  getRegistry(): Record<string, string>;
  log(id: string, label: string, detail: string): void;
  reset(): void;
  getDebug(): Record<string, { t: number; label: string; detail: string }[]>;
  extract(text: string): string;
}

export interface WidgetState {
  widgetId: string;
  state: Record<string, unknown>;
}

export interface WidgetDefinition {
  id: string;
  key?: string;
  code: string;
  version?: number | string;
}

export interface IWidgetController {
  registerWidget(id: string, code: string, key?: string): void;
  getWidgetCode(id: string): string | undefined;
  saveState(id: string, state: Record<string, unknown>): Promise<void>;
  loadState(id: string): Record<string, unknown>;
  handleIframeMessage(event: MessageEvent): void;
}

export interface IWidgetIframeBuilder {
  buildSrcDoc(id: string, code: string, initialState?: Record<string, unknown>): string;
  createIframeElement(id: string, key: string | undefined, code: string, initialState?: Record<string, unknown>): HTMLIFrameElement;
}

export interface CardLayout {
  key: string;
  x: number;
  y: number;
  w: number;
  h: number;
  minimized: boolean;
  code: string;
}

export interface ICanvasCardManager {
  addCard(key: string, code: string, layout?: Partial<CardLayout>): HTMLElement | null;
  removeCard(key: string): void;
  getCardLayouts(): CardLayout[];
  isPinned(key: string): boolean;
  bringToFront(key: string): void;
  clear(): void;
  getCard(key: string): HTMLElement | null;
  onLayoutChange?: () => void;
}

export interface ILayoutStore {
  saveLayout(sessionId: string, cards: CardLayout[]): void;
  loadLayout(sessionId: string): CardLayout[];
  clear(sessionId: string): void;
}
