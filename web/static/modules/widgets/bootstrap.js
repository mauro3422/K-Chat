/**
 * Kairos Widgets — Bootstrap
 *
 * Instala la API pública en `window` para compatibilidad histórica.
 */
import { KairosWidgets, initAll, startMessageHandler } from './index.js';

if (!window.KairosWidgets) {
  window.KairosWidgets = KairosWidgets;
}
window.KairosWidgets.initAll = initAll;
window.KairosWidgets.startMessageHandler = startMessageHandler;
