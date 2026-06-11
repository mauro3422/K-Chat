/**
 * Kairos Widgets — Toolbar Core
 *
 * Creación del toolbar UI y helpers de botones.
 */
import { createToolbarButton } from './ui-helpers.js';
import { buildIframeSrc } from './iframe-builder.js';
import { KairosWidgets } from './core.js';
import { openEditor } from './toolbar-editor.js';
import { toggleHistoryList } from './toolbar-history.js';

export function createToolbar(container, id, key, code, hashId) {
    var oldToolbar = container.querySelector('.widget-toolbar');
    if (oldToolbar) return;

    var toolbar = document.createElement('div');
    toolbar.className = 'widget-toolbar';
    toolbar.style.display = 'flex';
    toolbar.style.flexWrap = 'wrap';
    toolbar.style.justifyContent = 'space-between';
    toolbar.style.alignItems = 'center';
    toolbar.style.gap = '4px';
    toolbar.style.background = '#10141b';
    toolbar.style.border = '1px solid #30363d';
    toolbar.style.borderBottom = 'none';
    toolbar.style.borderRadius = '8px 8px 0 0';
    toolbar.style.padding = '6px 12px';
    toolbar.style.fontSize = '11px';
    toolbar.style.fontFamily = 'monospace';
    toolbar.style.color = '#00ff99';

    var leftSide = document.createElement('div');
    leftSide.className = 'widget-toolbar-left';
    var leftSpan = document.createElement('span');
    leftSpan.textContent = key ? '🛸 WIDGET: ' + key.toUpperCase() : '🧪 WIDGET TEMPORAL';
    leftSide.appendChild(leftSpan);
    toolbar.appendChild(leftSide);

    if (key) {
        var isCached = window.widgetStates && window.widgetStates['_code_' + key];
        if (!isCached) {
            fetchVersionLabel(key, leftSide);
        }
    }

    var rightSide = document.createElement('div');
    rightSide.className = 'widget-toolbar-right';
    rightSide.style.display = 'flex';
    rightSide.style.gap = '8px';

    if (key) {
        var btnEdit = createToolbarButton({
            label: 'EDITAR',
            border: '1px solid #00ff99',
            color: '#00ff99',
            onClick: function onEditClick() {
                openEditor(container, id, key, code);
            }
        });
        rightSide.appendChild(btnEdit);

        var btnHist = createToolbarButton({
            label: 'HISTORIAL',
            border: '1px solid #00ffff',
            color: '#00ffff',
            onClick: function onHistoryClick() {
                toggleHistoryList(container, id, key);
            }
        });
        rightSide.appendChild(btnHist);
    }

    var btnReset = createToolbarButton({
        label: 'RESET',
        border: '1px solid #ff3366',
        color: '#ff3366',
        onClick: function onResetClick() {
            if (confirm('¿Reiniciar estado del widget?')) {
                window.widgetStates = window.widgetStates || {};
                window.widgetStates[hashId] = null;
                fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(hashId) + '/state', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ state: '{}' })
                }).then(function onResetResponse() {
                    var iframe = container.querySelector('iframe');
                    if (iframe) {
                        iframe.srcdoc = buildIframeSrc(id, KairosWidgets._registry[id] || code, 'null');
                    }
                }).catch(function(err) { console.error('Widget reset failed:', err); });
            }
        }
    });
    rightSide.appendChild(btnReset);

    toolbar.appendChild(rightSide);
    container.insertBefore(toolbar, container.firstChild);
}

function fetchVersionLabel(key, leftSide) {
    fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(key) + '/code')
        .then(function(r) {
            if (!r.ok) throw new Error('not-found');
            return r.json();
        })
        .then(function(data) {
            var vSpan = document.createElement('span');
            vSpan.className = 'widget-v-label';
            vSpan.style.color = '#00ffff';
            vSpan.style.marginLeft = '8px';
            vSpan.textContent = '[V' + data.version + ']';
            leftSide.appendChild(vSpan);
        }).catch(function(){});
}
