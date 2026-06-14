/**
 * Kairos Widgets — Toolbar History
 *
 * Listado de versiones, fetch de historial, navegación y carga de código.
 */
import { ApiClient } from '../api-client.js';
import { SessionContext } from '../session-context.js';
import { WidgetManager } from './core.js';
import { buildIframeSrc } from './iframe-builder.js';
import stateManager from './state-manager.js';

export function toggleHistoryList(container, id, key) {
    var oldList = container.querySelector('.widget-history-list');
    if (oldList) {
        oldList.parentNode.removeChild(oldList);
        return;
    }

    var historyDiv = document.createElement('div');
    historyDiv.className = 'widget-history-container';

    var title = document.createElement('div');
    title.className = 'widget-history-title';
    title.textContent = 'VERSIONES DISPONIBLES:';
    historyDiv.appendChild(title);

    ApiClient.loadWidgetVersions(SessionContext.getSessionId(), key)
        .then(function parseVersionsResponse(r) { return r.json(); })
        .then(function renderVersionList(data) {
            if (!data.versions || data.versions.length === 0) {
                var item = document.createElement('div');
                item.textContent = 'Sin historial.';
                historyDiv.appendChild(item);
            } else {
                data.versions.forEach(function renderVersionItem(v) {
                    var item = document.createElement('div');
                    item.className = 'widget-history-item';

                    var leftText = document.createElement('span');
                    leftText.className = 'widget-history-text';
                    leftText.textContent = 'V' + v.version + ': ' + (v.description || 'Sin descripción');
                    item.appendChild(leftText);

                    var link = document.createElement('span');
                    link.className = 'widget-history-link';
                    link.textContent = '[CARGAR]';
                    item.appendChild(link);

                    item.onclick = function onVersionClick() {
                        ApiClient.loadWidgetVersionCode(SessionContext.getSessionId(), key, v.version)
                            .then(function parseVersionCodeResponse(r) { return r.json(); })
                            .then(function loadVersionCode(verData) {
                                WidgetManager._registry[id] = verData.code;
                                var iframe = container.querySelector('iframe');
                                if (iframe) {
                                    var hashId = key;
                                    var stateStr = stateManager.getState(hashId);
                                    var safeStateStr = stateStr !== null ? JSON.stringify(stateStr) : 'null';
                                    iframe.srcdoc = buildIframeSrc(id, verData.code, safeStateStr);
                                }
                                var label = container.querySelector('.widget-toolbar-left .widget-v-label');
                                if (label) {
                                    label.textContent = '[V' + v.version + ']';
                                }
                                historyDiv.parentNode.removeChild(historyDiv);
                            }).catch(function(err) { console.error('Version load failed:', err); });
                    };
                    historyDiv.appendChild(item);
                });
            }
        }).catch(function onHistoryError(err) {
            var errorDiv = document.createElement('div');
            errorDiv.className = 'widget-history-error';
            errorDiv.textContent = 'Error: ' + err.message;
            historyDiv.appendChild(errorDiv);
        });

    var toolbar = container.querySelector('.widget-toolbar');
    if (toolbar) {
        toolbar.parentNode.insertBefore(historyDiv, toolbar.nextSibling);
    } else {
        container.appendChild(historyDiv);
    }
}
