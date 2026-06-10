/**
 * Kairos Widgets — IFrame Mounting
 *
 * Inicialización de contenedores de widgets.
 */
import { log, KairosWidgets } from './core.js';
import { createIframe } from './iframe-builder.js';

let _widgetObserver = null;

export function initAll(parentEl, forceImmediate) {
    var scope = parentEl || document.body;
    var containers = scope.querySelectorAll('.interactive-widget-container');
    for (var i = 0; i < containers.length; i++) {
        var container = containers[i];
        if (container.dataset.initialized) continue;
        var id = container.getAttribute('data-widget-id');
        var code = KairosWidgets._registry[id];
        var key = container.getAttribute('data-widget-key');
        if (code === undefined && !key) continue;

        log(id, 'init', 'code=' + (code ? code.length : 0) + 'b key=' + key + ' padre=' + (parentEl.className || parentEl.id || '?'));

        if (forceImmediate || !_widgetObserver) {
            createIframe(container, id, code);
        } else {
            if (container.dataset.observed) continue;
            container.dataset.observed = '1';
            _widgetObserver.observe(container);
            log(id, 'lazy-queue', 'esperando visibilidad');
        }
    }
}

export function getWidgetObserver() {
    return _widgetObserver;
}

export function setWidgetObserver(observer) {
    _widgetObserver = observer;
}
