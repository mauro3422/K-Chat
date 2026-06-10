/**
 * Kairos Widgets — Public API
 *
 * Expone window.KairosWidgets con la interfaz original.
 * Ensambla core + iframe-builder + toolbar + iframe + messaging.
 */
import { KairosWidgets, extract, log, reset, nextIndex } from './core.js';
import { buildIframeSrc, createIframe } from './iframe-builder.js';
import { createToolbar } from './toolbar-core.js';
import { initAll } from './iframe.js';
import { startMessageHandler } from './messaging.js';

startMessageHandler();

export { KairosWidgets, extract, initAll, log, reset, startMessageHandler, buildIframeSrc, nextIndex };
export { createIframe };
export { createToolbar };

export const registry = KairosWidgets._registry;
export const debug = KairosWidgets._debug;
export const index = KairosWidgets._index;
