/**
 * WidgetRegistry — stores widget code and provides sequential widget IDs.
 * Port of widgets/core.js (nextIndex, extract, registry) into TS.
 *
 * Matches production:
 * - Sequential widget IDs (widget-0, widget-1, ...)
 * - extract() replaces ```html-widget blocks and [Widget:key] tags with container divs
 * - FNV-1a 32-bit hashing for state keys (not for IDs)
 *
 * NOW INSTANCE-BASED: inject via IWidgetRegistry interface.
 * For convenience, a default singleton is exported at module level.
 */

import { IWidgetRegistry } from '../../types/widgets';

const WIDGET_CONTAINER_CLASS = 'interactive-widget-container';

/** Regex for ```html-widget [key] \n ... \n``` blocks */
const INLINE_WIDGET_BLOCK_RE = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)(?:\n```|$)/g;

/** Regex for [Widget:key] or [Widget key] inline tags */
const INLINE_WIDGET_TAG_RE = /\[Widget:?\s*([\w\-]+)\]/gi;

/**
 * Normalize widget code: fix optional chaining assignment syntax.
 */
function normalizeWidgetCode(code: string): string {
  return String(code || '').replace(/\?\.([\w.]+)\s*=(?!=)/g, '.$1 =');
}

/**
 * FNV-1a 32-bit hash (port of the JS version in core.js).
 * Returns 8-char hex string.
 */
export function fnv1a_32(str: string): string {
  const utf8 = unescape(encodeURIComponent(str));
  let h = 2166136261;
  for (let i = 0; i < utf8.length; i++) {
    h = h ^ utf8.charCodeAt(i);
    h = Math.imul(h, 16777619) >>> 0;
  }
  return ('00000000' + h.toString(16)).slice(-8);
}

export class WidgetRegistry implements IWidgetRegistry {
  /** Sequential widget index counter */
  private _index = 0;

  /** Registry of widget code by sequential ID: { 'widget-0': '...code...' } */
  private _registry: Record<string, string> = {};

  /** Debug log per widget */
  private _debug: Record<string, { t: number; label: string; detail: string }[]> = {};

  /** Reset for a new session */
  reset(): void {
    this._index = 0;
    this._registry = {};
    this._debug = {};
  }

  /** Get next sequential widget ID (widget-0, widget-1, ...) */
  nextIndex(): string {
    const id = 'widget-' + this._index;
    this._index++;
    return id;
  }

  /** Get the current index value */
  getIndex(): number {
    return this._index;
  }

  /** Get registry copy */
  getRegistry(): Record<string, string> {
    return this._registry;
  }

  /** Get debug log */
  getDebug(): Record<string, { t: number; label: string; detail: string }[]> {
    return this._debug;
  }

  /** Register code and return sequential widget ID */
  register(code: string, key?: string): string {
    const id = this.nextIndex();
    this._registry[id] = code;
    return id;
  }

  /** Get code by sequential ID */
  getCode(id: string): string | undefined {
    return this._registry[id];
  }

  /** Log a widget lifecycle event */
  log(id: string, label: string, detail: string): void {
    if (!this._debug[id]) this._debug[id] = [];
    this._debug[id].push({
      t: Date.now(),
      label,
      detail: String(detail || '').substring(0, 200),
    });
    if (this._debug[id].length > 50) this._debug[id].shift();
    // Mirror to console
    console.log(`[W][${id}] ${label} ${detail}`);
  }

  /**
   * Extract widget blocks/tags from markdown text and replace with container divs.
   *
   * Production equivalent: WidgetManager.extract(text) in widgets/core.js
   *
   * Steps:
   * 1. Find ```html-widget [key] \n code \n ``` blocks → replace with <div class="interactive-widget-container" data-widget-id="widget-N" data-widget-key="key">
   * 2. Find [Widget: key] tags → replace with same container div
   *
   * Returns the text with widget containers injected (for marked.parse to render around them).
   */
  extract(text: string): string {
    if (!text) return '';

    // Find all standard code blocks and inline code blocks that are NOT widgets
    const ignoredRanges: { start: number; end: number }[] = [];

    const codeBlockRegex = /```(html-widget)?[\s\S]*?(?:```|$)/g;
    let match: RegExpExecArray | null;
    while ((match = codeBlockRegex.exec(text)) !== null) {
      if (!match[1]) {
        ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
      }
    }

    const inlineRegex = /`[^`\n]+`/g;
    while ((match = inlineRegex.exec(text)) !== null) {
      ignoredRanges.push({ start: match.index, end: match.index + match[0].length });
    }

    function isIgnored(idx: number): boolean {
      for (const range of ignoredRanges) {
        if (idx >= range.start && idx < range.end) return true;
      }
      return false;
    }

    // 1. Parse markdown code blocks with optional key: ```html-widget [key]
    INLINE_WIDGET_BLOCK_RE.lastIndex = 0;
    text = text.replace(INLINE_WIDGET_BLOCK_RE, (match: string, key: string | undefined, code: string, offset: number) => {
      if (isIgnored(offset)) return match;
      const id = this.nextIndex();
      const normalizedCode = normalizeWidgetCode(code);
      this._registry[id] = normalizedCode;
      return `<div class="${WIDGET_CONTAINER_CLASS}" data-widget-id="${id}"${key ? ` data-widget-key="${key}"` : ''}></div>`;
    });

    // 2. Parse inline tags like [Widget: key] or [Widget key] to load saved widgets
    const seenKeys: Record<string, boolean> = {};
    INLINE_WIDGET_TAG_RE.lastIndex = 0;
    text = text.replace(INLINE_WIDGET_TAG_RE, (match: string, key: string, offset: number) => {
      if (isIgnored(offset)) return match;
      const lowerKey = key.toLowerCase();
      if (seenKeys[lowerKey]) return '';
      seenKeys[lowerKey] = true;
      const id = this.nextIndex();
      return `<div class="${WIDGET_CONTAINER_CLASS}" data-widget-id="${id}" data-widget-key="${key}"></div>`;
    });

    return text;
  }
}

/** Default singleton instance for backward compatibility and simple use cases */
export const defaultWidgetRegistry = new WidgetRegistry();
