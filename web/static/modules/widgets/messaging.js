/**
 * Kairos Widgets — Messaging & Persistence
 *
 * Escucha postMessage desde los iframes y gestiona IntersectionObserver global.
 */
import { log, KairosWidgets, fnv1a_32 } from './core.js';
import { createIframe } from './iframe-builder.js';
import { getWidgetObserver, setWidgetObserver } from './iframe.js';

export function startMessageHandler() {
    if (window.IntersectionObserver && !getWidgetObserver()) {
        setWidgetObserver(new IntersectionObserver(function(entries) {
            for (var j = 0; j < entries.length; j++) {
                var entry = entries[j];
                if (entry.isIntersecting) {
                    var container = entry.target;
                    var id = container.getAttribute('data-widget-id');
                    var code = KairosWidgets._registry[id];
                    var key = container.getAttribute('data-widget-key');
                    if ((code !== undefined || key) && !container.dataset.initialized) {
                        log(id, 'lazy-load', 'visible en viewport');
                        createIframe(container, id, code);
                    }
                    getWidgetObserver().unobserve(container);
                }
            }
        }, { rootMargin: '100px' }));
    }

    window.addEventListener('message', function(event) {
        var isWidgetMessage = event.data && (event.data.type === 'resize-iframe' || event.data.type === 'save-widget-state' || event.data.type === 'widget-error');
        if (isWidgetMessage && event.origin !== 'null' && event.origin !== window.location.origin) return;
        if (!isWidgetMessage && event.origin !== window.location.origin) return;
        if (!event.data) return;

        if (event.data.type === 'resize-iframe') {
            var iframe = document.querySelector('[data-widget-id="' + event.data.id + '"] iframe');
            if (iframe) {
                iframe.style.height = (event.data.height + 4) + 'px';
                log(event.data.id, 'altura', event.data.height + 'px -> ' + (event.data.height + 4) + 'px');
            }
        } else if (event.data.type === 'save-widget-state') {
            var code = KairosWidgets._registry[event.data.id];
            var hashId = code ? 'widget-' + fnv1a_32(code) : event.data.id;
            window.widgetStates = window.widgetStates || {};
            window.widgetStates[hashId] = event.data.state;
            // Also persist any _code_ entries (widget code cache)
            var codeEntries = {};
            Object.keys(window.widgetStates).forEach(function(k) {
                if (k.indexOf('_code_') === 0) codeEntries[k] = window.widgetStates[k];
            });
            fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(hashId) + '/state', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ state: event.data.state, codeEntries: codeEntries })
            }).catch(function(err) { console.error('Widget state save failed:', err); });
        } else if (event.data.type === 'widget-error') {
            console.error('[Widget ' + event.data.id + '] ' + event.data.message + ' (linea ' + event.data.line + ')');
            log(event.data.id, 'ERROR', event.data.message + ' L:' + event.data.line);
        }
    });
}
window.KairosWidgets = window.KairosWidgets || {};
window.KairosWidgets.startMessageHandler = startMessageHandler;
