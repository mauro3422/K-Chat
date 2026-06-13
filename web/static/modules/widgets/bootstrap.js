/**
 * Kairos Widgets — Bootstrap
 *
 * Instala la API pública en `window` para compatibilidad histórica.
 */
import { KairosWidgets, initAll, startMessageHandler } from './index.js';

// window assignments removed — KairosWidgets is imported directly by all consumers
// if (!window.KairosWidgets) {
//   window.KairosWidgets = KairosWidgets;
// }
// window.KairosWidgets.initAll = initAll;
// window.KairosWidgets.startMessageHandler = startMessageHandler;
