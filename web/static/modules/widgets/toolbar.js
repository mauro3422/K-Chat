/**
 * Kairos Widgets — Toolbar (re-export)
 *
 * Re-exporta la API pública de los módulos toolbar-core, toolbar-editor y toolbar-history.
 * El bootstrap de widgets instala la compatibilidad global aparte del núcleo.
 */
export { createToolbar } from './toolbar-core.js';
export { openEditor } from './toolbar-editor.js';
export { toggleHistoryList } from './toolbar-history.js';
