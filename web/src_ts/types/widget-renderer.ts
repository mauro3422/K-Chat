import { IDebugManager } from './debug';

export interface WidgetMatch {
  index: number;
  end: number;
  key?: string;
  code?: string;
  isNew: boolean;
  codeBlock: boolean;
}

export interface ProcessResult {
  textToRender: string;
  incompleteTail: string;
  widgetMatches: WidgetMatch[];
}

export interface IWidgetContainerRenderer {
  processWidgetContainers(
    fullText: string,
    bodyDiv: HTMLElement,
    existingByKey: Record<string, HTMLElement>,
    renderedKeys: Record<string, boolean>,
  ): ProcessResult;
  destroyAll(container: HTMLElement): void;
  reset(): void;
}
