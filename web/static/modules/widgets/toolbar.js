/**
 * Kairos Widgets — Toolbar (re-export)
 *
 * Re-exporta la API pública de los módulos toolbar-core, toolbar-editor y toolbar-history.
 * Los módulos se cargan antes y adjuntan sus funciones a window.KairosWidgets.
 */
window.KairosWidgets = (function(api) {

    return api;
})(window.KairosWidgets || {});
