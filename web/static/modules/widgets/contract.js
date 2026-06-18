export const WIDGET_STATE_CODE_PREFIX = '_code_';

export function normalizeWidgetCode(code) {
  return String(code || '').replace(/\?\.(\w[\w.]*)\s*=(?!=)/g, '.$1 =');
}

export function widgetCodeEntryKey(key) {
  return `${WIDGET_STATE_CODE_PREFIX}${key}`;
}

export function isWidgetCodeEntry(key) {
  return typeof key === 'string' && key.startsWith(WIDGET_STATE_CODE_PREFIX);
}
