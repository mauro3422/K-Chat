/**
 * Kairos Widgets — Bootstrap
 *
 * Instala la API pública en `window` para compatibilidad histórica
 * y arranca el message handler una sola vez.
 */
import { KairosWidgets, initAll, startMessageHandler } from './index.js';

if (!window.KairosWidgets) {
  window.KairosWidgets = KairosWidgets;
}
window.KairosWidgets.initAll = initAll;
window.KairosWidgets.startMessageHandler = startMessageHandler;

startMessageHandler();
