import { IWidgetRegistry } from './widgets';
import { IWidgetStateManager } from '../core/widget/WidgetStateManager';

export interface IIframeBuilder {
  stateManager?: IWidgetStateManager;
  buildSrcDoc(id: string, code: string, initialState?: Record<string, unknown>): string;
  initAll(parentEl: HTMLElement, forceImmediate?: boolean): void;
  handleMessage(event: MessageEvent): void;
  createCanvasIframe(container: HTMLElement, widgetKey: string, code: string): HTMLIFrameElement;
  reset(): void;
}
