/**
 * Kairos Widgets — Messaging & Persistence
 *
 * Escucha postMessage desde los iframes y gestiona IntersectionObserver global.
 */
import { SessionContext } from '../session-context.js';
import { log, WidgetManager, fnv1a_32 } from './core.js';
import { createIframe } from './iframe-builder.js';
import { getWidgetObserver, setWidgetObserver } from './iframe.js';
import stateManager from './state-manager.js';
import { isWidgetCodeEntry } from './contract.js';
import { ApiClient } from '../api-client.js';

export function startMessageHandler(deps) {
    var eventTarget = deps && deps.eventTarget ? deps.eventTarget : window;
    var locationOrigin = deps && deps.locationOrigin ? deps.locationOrigin : window.location.origin;
    var Observer = deps && deps.Observer ? deps.Observer : IntersectionObserver;

    if (Observer && !getWidgetObserver()) {
        setWidgetObserver(new Observer(function(entries) {
            for (var j = 0; j < entries.length; j++) {
                var entry = entries[j];
                if (entry.isIntersecting) {
                    var container = entry.target;
                    var id = container.getAttribute('data-widget-id');
                    var code = WidgetManager._registry[id];
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

    eventTarget.addEventListener('message', function(event) {
        var isWidgetMessage = event.data && (event.data.type === 'resize-iframe' || event.data.type === 'save-widget-state' || event.data.type === 'widget-error');
        if (isWidgetMessage && event.origin !== 'null' && event.origin !== locationOrigin) return;
        if (!isWidgetMessage && event.origin !== locationOrigin) return;
        if (!event.data) return;

        if (event.data.type === 'resize-iframe') {
            var iframe = document.querySelector('[data-widget-id="' + event.data.id + '"] iframe');
            if (iframe) {
                iframe.style.height = (event.data.height + 4) + 'px';
                log(event.data.id, 'altura', event.data.height + 'px -> ' + (event.data.height + 4) + 'px');
            }
        } else if (event.data.type === 'save-widget-state') {
            var code = WidgetManager._registry[event.data.id];
            var hashId = code ? 'widget-' + fnv1a_32(code) : event.data.id;
            stateManager.setState(hashId, event.data.state);
            var codeEntries = {};
            var allState = stateManager.toJSON();
            Object.keys(allState).forEach(function(k) {
                if (isWidgetCodeEntry(k)) codeEntries[k] = allState[k];
            });
            ApiClient.saveWidgetState(SessionContext.getSessionId(), hashId, event.data.state)
              .catch(function(err) { console.error('Widget state save failed:', err); });
            Object.keys(codeEntries).forEach(function(k) {
              ApiClient.saveWidgetState(SessionContext.getSessionId(), k, codeEntries[k])
                .catch(function(err) { console.error('Widget code entry save failed:', err); });
            });
        } else if (event.data.type === 'widget-error') {
            console.error('[Widget ' + event.data.id + '] ' + event.data.message + ' (linea ' + event.data.line + ')');
            log(event.data.id, 'ERROR', event.data.message + ' L:' + event.data.line);
        }
    });
}
