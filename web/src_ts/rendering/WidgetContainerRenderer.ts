import { IDebugManager } from '../types/debug';
import { WidgetMatch, ProcessResult, IWidgetContainerRenderer } from '../types/widget-renderer';
import { IframeBuilder } from './IframeBuilder';
import { C } from '../core/DomContracts';

/**
 * WidgetContainerRenderer — production-matching widget detection.
 *
 * NOW ONLY CALCULATES STRUCTURE — does NOT modify the DOM.
 * The ContentHandler applies DOM changes incrementally (preserving iframes).
 *
 * Mirrors: web/static/modules/widget-container-renderer.js
 */
export class WidgetContainerRenderer implements IWidgetContainerRenderer {
  private debug?: IDebugManager;
  private iframeBuilder: IframeBuilder;

  constructor(iframeBuilder: IframeBuilder, debug?: IDebugManager) {
    this.iframeBuilder = iframeBuilder;
    this.debug = debug;
  }

  /**
   * Detect widgets in fullText and calculate the structure.
   * Does NOT modify bodyDiv — only returns the analysis.
   */
  processWidgetContainers(
    fullText: string,
    bodyDiv: HTMLElement,
    existingByKey: Record<string, HTMLElement>,
    renderedKeys: Record<string, boolean>,
  ): ProcessResult {
    // ── 1. Find all ignored ranges (non-widget code + inline code) ───────
    const ignoredRanges: { start: number; end: number }[] = [];

    const codeBlockRegex = /```(html-widget)?[\s\S]*?(?:```|$)/g;
    let match: RegExpExecArray | null;
    while ((match = codeBlockRegex.exec(fullText)) !== null) {
      if (!match[1]) {
        ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
      }
    }

    const inlineRegex = /`[^`\n]+`/g;
    while ((match = inlineRegex.exec(fullText)) !== null) {
      ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
    }

    const isIgnored = (idx: number): boolean => {
      for (const range of ignoredRanges) {
        if (idx >= range.start && idx < range.end) return true;
      }
      return false;
    };

    // ── 2. Find widget matches (tags + code blocks) ────────────────────
    const widgetMatches: WidgetMatch[] = [];

    // 2a. [Widget: key] tags
    const tagRegex = /\[Widget:?\s*([\w\-]+)\]/gi;
    let m: RegExpExecArray | null;
    while ((m = tagRegex.exec(fullText)) !== null) {
      if (!isIgnored(m.index)) {
        widgetMatches.push({
          index: m.index,
          end: m.index + m[0].length,
          key: m[1],
          isNew: !renderedKeys[m[1]],
          codeBlock: false,
        });
        renderedKeys[m[1]] = true;
      }
    }

    // 2b. ```html-widget [key] \n code \n ``` blocks
    const widgetBlockRegex = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)\n```/g;
    while ((m = widgetBlockRegex.exec(fullText)) !== null) {
      if (!isIgnored(m.index)) {
        const cKey = m[1] || undefined;
        const innerCode = m[2] || '';
        const dedupKey = cKey || '_pos_' + m.index;
        widgetMatches.push({
          index: m.index,
          end: m.index + m[0].length,
          key: cKey,
          code: innerCode,
          isNew: !renderedKeys[dedupKey],
          codeBlock: true,
        });
        renderedKeys[dedupKey] = true;
      }
    }

    // ── 3. Sort and filter (non-overlapping) ──────────────────────────
    widgetMatches.sort((a, b) => a.index - b.index);
    const filtered: WidgetMatch[] = [];
    let lastEnd = 0;
    for (const wm of widgetMatches) {
      if (wm.index >= lastEnd) {
        filtered.push(wm);
        lastEnd = wm.end;
      }
    }

    // ── 4. Handle incomplete code blocks ─────────────────────────────
    let textToRender = fullText;
    let incompleteTail = '';

    const lastOpen = fullText.lastIndexOf('```html-widget');
    if (lastOpen >= 0 && !isIgnored(lastOpen)) {
      const afterOpen = fullText.substring(lastOpen);
      const completeBlock = afterOpen.match(/^```html-widget(?:\s+[\w\-]+)?\s*\n[\s\S]*?\n```/);
      if (!completeBlock) {
        textToRender = fullText.substring(0, lastOpen);
        incompleteTail = fullText.substring(lastOpen);
      }
    }

    // ── 5. Remove code blocks from textToRender ──────────────────────
    for (const wm of filtered) {
      if (wm.codeBlock && textToRender.length >= wm.end) {
        textToRender = textToRender.substring(0, wm.index) + textToRender.substring(wm.end);
        const shift = wm.end - wm.index;
        wm.end = wm.index;
        for (let adj = filtered.indexOf(wm) + 1; adj < filtered.length; adj++) {
          filtered[adj].index -= shift;
          filtered[adj].end -= shift;
        }
      }
    }

    return { textToRender, incompleteTail, widgetMatches: filtered };
  }

  destroyAll(container: HTMLElement): void {
    const widgetContainers = container.querySelectorAll(
      '.' + C.WIDGET_CONTAINER
    );
    widgetContainers.forEach((con) => {
      this.iframeBuilder.destroyContainer(con as HTMLElement);
    });
  }

  reset(): void {
    // No state to reset
  }
}
