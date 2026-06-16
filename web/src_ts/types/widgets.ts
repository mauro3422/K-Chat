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
