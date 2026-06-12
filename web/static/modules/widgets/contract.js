import C from '../dom-contracts.js';

export const WIDGET_CONTAINER_CLASS = C.WIDGET_CONTAINER;
export const WIDGET_STATE_CODE_PREFIX = '_code_';
export const INLINE_WIDGET_BLOCK_RE = /```html-widget(?:\s+([\w\-]+))?\s*\n([\s\S]*?)(?:\n```|$)/g;
export const INLINE_WIDGET_TAG_RE = /\[Widget:?\s*([\w\-]+)\]/gi;

export function normalizeWidgetCode(code) {
    return String(code || '').replace(/\?\.([\w.]+)\s*=(?!=)/g, '.$1 =');
}

export function widgetCodeEntryKey(widgetKey) {
    return WIDGET_STATE_CODE_PREFIX + String(widgetKey || '').trim();
}

export function isWidgetCodeEntry(key) {
    return String(key || '').indexOf(WIDGET_STATE_CODE_PREFIX) === 0;
}
