/**
 * Kairos Widgets — IFrame Mounting
 *
 * Inicialización de contenedores de widgets.
 */
window.KairosWidgets = (function(api) {

    api._widgetObserver = null;

    api.initAll = function(parentEl, forceImmediate) {
        var scope = parentEl || document.body;
        var containers = scope.querySelectorAll('.interactive-widget-container');
        for (var i = 0; i < containers.length; i++) {
            var container = containers[i];
            if (container.dataset.initialized) continue;
            var id = container.getAttribute('data-widget-id');
            var code = api._registry[id];
            var key = container.getAttribute('data-widget-key');
            if (code === undefined && !key) continue;

            api.log(id, 'init', 'code=' + (code ? code.length : 0) + 'b key=' + key + ' padre=' + (parentEl.className || parentEl.id || '?'));

            if (forceImmediate || !api._widgetObserver) {
                api.createIframe(container, id, code);
            } else {
                if (container.dataset.observed) continue;
                container.dataset.observed = '1';
                api._widgetObserver.observe(container);
                api.log(id, 'lazy-queue', 'esperando visibilidad');
            }
        }
    };

    return api;
})(window.KairosWidgets || {});
