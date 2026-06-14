/**
 * Kairos Widgets — Public API
 *
 * Exporta la API pública sin tocar globals.
 */
import { WidgetManager, extract, log, reset, nextIndex } from './core.js';
import { buildIframeSrc, createIframe } from './iframe-builder.js';
import { createToolbar } from './toolbar-core.js';
import { initAll } from './iframe.js';
import { startMessageHandler } from './messaging.js';

export { WidgetManager, extract, initAll, log, reset, startMessageHandler, buildIframeSrc, nextIndex };
export { createIframe };
export { createToolbar };

export const registry = WidgetManager._registry;
export const debug = WidgetManager._debug;
export const index = WidgetManager._index;
