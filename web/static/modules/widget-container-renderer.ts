import { WidgetContainerRenderer as TsWidgetContainerRenderer } from '../../src_ts/rendering/WidgetContainerRenderer';

const renderer = new TsWidgetContainerRenderer({} as any);

export function processWidgetContainers(
  fullText: string,
  bodyDiv: HTMLElement,
  existingByKey: Record<string, HTMLElement>,
  renderedKeys: Record<string, boolean>,
):
  { textToRender: string; incompleteTail: string; widgetMatches: Array<{ index: number; end: number; key?: string; code?: string; isNew: boolean; codeBlock: boolean }> } {
  return renderer.processWidgetContainers(fullText, bodyDiv, existingByKey, renderedKeys);
}
