/**
 * Kairos Widgets — Toolbar History
 *
 * Listado de versiones, fetch de historial, navegación y carga de código.
 */
import { KairosWidgets } from './core.js';
import { buildIframeSrc } from './iframe-builder.js';

export function toggleHistoryList(container, id, key) {
    var oldList = container.querySelector('.widget-history-list');
    if (oldList) {
        oldList.parentNode.removeChild(oldList);
        return;
    }

    var historyDiv = document.createElement('div');
    historyDiv.className = 'widget-history-list';
    historyDiv.style.background = '#10141b';
    historyDiv.style.border = '1px solid #00ffff';
    historyDiv.style.borderRadius = '4px';
    historyDiv.style.padding = '8px';
    historyDiv.style.marginTop = '4px';
    historyDiv.style.fontSize = '10px';
    historyDiv.style.fontFamily = 'monospace';

    var title = document.createElement('div');
    title.textContent = '⏳ VERSIONES DISPONIBLES:';
    title.style.color = '#00ffff';
    title.style.fontWeight = 'bold';
    title.style.marginBottom = '6px';
    historyDiv.appendChild(title);

    fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(key) + '/versions')
        .then(function parseVersionsResponse(r) { return r.json(); })
        .then(function renderVersionList(data) {
            if (!data.versions || data.versions.length === 0) {
                var item = document.createElement('div');
                item.textContent = 'Sin historial.';
                historyDiv.appendChild(item);
            } else {
                data.versions.forEach(function renderVersionItem(v) {
                    var item = document.createElement('div');
                    item.style.display = 'flex';
                    item.style.justifyContent = 'space-between';
                    item.style.padding = '4px';
                    item.style.borderBottom = '1px solid #21262d';
                    item.style.cursor = 'pointer';

                    var leftText = document.createElement('span');
                    leftText.style.color = '#c9d1d9';
                    leftText.textContent = 'V' + v.version + ': ' + (v.description || 'Sin descripción');
                    item.appendChild(leftText);

                    var link = document.createElement('span');
                    link.style.color = '#00ffff';
                    link.textContent = '[CARGAR]';
                    item.appendChild(link);

                    item.onclick = function onVersionClick() {
                        fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(key) + '/versions/' + v.version + '/code')
                            .then(function parseVersionCodeResponse(r) { return r.json(); })
                            .then(function loadVersionCode(verData) {
                                KairosWidgets._registry[id] = verData.code;
                                var iframe = container.querySelector('iframe');
                                if (iframe) {
                                    var hashId = key;
                                    var stateStr = null;
                                    if (window.widgetStates) {
                                        stateStr = window.widgetStates[hashId] || null;
                                    }
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
            errorDiv.style.color = '#ff3366';
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
