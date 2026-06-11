/**
 * Kairos Widgets — IFrame Mounting
 *
 * Inicialización de contenedores de widgets.
 */
import C from '../dom-contracts.js';
import { log, KairosWidgets } from './core.js';
import { createIframe } from './iframe-builder.js';

let _widgetObserver = null;

/**
 * WeakMap that tracks widget container state.
 * Primary source of truth — survives DOM destruction/recreation.
 * Maps container element -> { initialized: boolean, observed: boolean, widgetId: string }
 */
let _initializedWidgets = new WeakMap();

export function getInitializedWidgets() {
    return _initializedWidgets;
}

export function initAll(parentEl, forceImmediate) {
    var scope = parentEl || document.body;
    var containers = scope.querySelectorAll('.' + C.WIDGET_CONTAINER);
    for (var i = 0; i < containers.length; i++) {
        var container = containers[i];
        var wmState = _initializedWidgets.get(container);
        if (wmState && wmState.initialized) continue;
        if (!forceImmediate && wmState && wmState.observed) continue;
        var id = container.getAttribute('data-widget-id');
        var code = KairosWidgets._registry[id];
        var key = container.getAttribute('data-widget-key');
        if (code === undefined && !key) continue;

        log(id, 'init', 'code=' + (code ? code.length : 0) + 'b key=' + key + ' padre=' + (parentEl.className || parentEl.id || '?'));

        if (forceImmediate || !_widgetObserver) {
            createIframe(container, id, code);
            _initializedWidgets.set(container, { initialized: true, observed: true, widgetId: id });
        } else {
            _initializedWidgets.set(container, { initialized: false, observed: true, widgetId: id });
            container.dataset.observed = '1';
            _widgetObserver.observe(container);
            log(id, 'lazy-queue', 'esperando visibilidad');
        }
    }
}

export function reset() {
    _initializedWidgets = new WeakMap();
}

export function getWidgetObserver() {
    return _widgetObserver;
}

export function setWidgetObserver(observer) {
    _widgetObserver = observer;
}
window.KairosWidgets = window.KairosWidgets || {};
window.KairosWidgets.initAll = initAll;
window.KairosWidgets.setWidgetObserver = setWidgetObserver;
window.KairosWidgets.resetInitializedWidgets = reset;
