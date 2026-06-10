/**
 * Kairos Widgets — Messaging & Persistence
 *
 * Escucha postMessage desde los iframes y gestiona IntersectionObserver global.
 */
window.KairosWidgets = (function(api) {

    api.startMessageHandler = function() {
        if (window.IntersectionObserver && !api._widgetObserver) {
            api._widgetObserver = new IntersectionObserver(function(entries) {
                for (var j = 0; j < entries.length; j++) {
                    var entry = entries[j];
                    if (entry.isIntersecting) {
                        var container = entry.target;
                        var id = container.getAttribute('data-widget-id');
                        var code = api._registry[id];
                        var key = container.getAttribute('data-widget-key');
                        if ((code !== undefined || key) && !container.dataset.initialized) {
                            api.log(id, 'lazy-load', 'visible en viewport');
                            api.createIframe(container, id, code);
                        }
                        api._widgetObserver.unobserve(container);
                    }
                }
            }, { rootMargin: '100px' });
        }

        window.addEventListener('message', function(event) {
            if (event.origin !== window.location.origin) return;
            if (!event.data) return;

            if (event.data.type === 'resize-iframe') {
                var iframe = document.querySelector('[data-widget-id="' + event.data.id + '"] iframe');
                if (iframe) {
                    iframe.style.height = (event.data.height + 4) + 'px';
                    api.log(event.data.id, 'altura', event.data.height + 'px -> ' + (event.data.height + 4) + 'px');
                }
            } else if (event.data.type === 'save-widget-state') {
                var code = api._registry[event.data.id];
                var hashId = code ? 'widget-' + api.fnv1a_32(code) : event.data.id;
                window.widgetStates = window.widgetStates || {};
                window.widgetStates[hashId] = event.data.state;
                fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(hashId) + '/state', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ state: event.data.state })
                });
            } else if (event.data.type === 'widget-error') {
                console.error('[Widget ' + event.data.id + '] ' + event.data.message + ' (linea ' + event.data.line + ')');
                api.log(event.data.id, 'ERROR', event.data.message + ' L:' + event.data.line);
            }
        });
    };

    return api;
})(window.KairosWidgets || {});
