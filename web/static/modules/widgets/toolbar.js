/**
 * Kairos Widgets — Toolbar (re-export)
 *
 * Re-exporta la API pública de los módulos toolbar-core, toolbar-editor y toolbar-history.
 * Los módulos se cargan antes y adjuntan sus funciones a window.KairosWidgets.
 */
export { createToolbar } from './toolbar-core.js';
export { openEditor } from './toolbar-editor.js';
export { toggleHistoryList } from './toolbar-history.js';
