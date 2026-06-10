/**
 * Kairos Widgets — Public API
 *
 * Expone window.KairosWidgets con la interfaz original.
 * Ensambla core + iframe-builder + toolbar + iframe + messaging.
 */
window.KairosWidgets = (function(api) {
    api.startMessageHandler();

    return {
        extract: api.extract,
        initAll: api.initAll,
        log: api.log,
        reset: api.reset,
        startMessageHandler: api.startMessageHandler,
        buildIframeSrc: api.buildIframeSrc,
        nextIndex: api.nextIndex,
        get registry() { return api._registry; },
        get debug() { return api._debug; },
        get index() { return api._index; }
    };
})(window.KairosWidgets || {});
