/**
 * Kairos Widgets — Toolbar Core
 *
 * Creación del toolbar UI y helpers de botones.
 */
import { ApiClient } from '../api-client.js';
import { SessionContext } from '../session-context.js';
import { createToolbarButton } from './ui-helpers.js';
import { buildIframeSrc } from './iframe-builder.js';
import { WidgetManager } from './core.js';
import { openEditor } from './toolbar-editor.js';
import { toggleHistoryList } from './toolbar-history.js';
import stateManager from './state-manager.js';

export function createToolbar(container, id, key, code, hashId) {
    var oldToolbar = container.querySelector('.widget-toolbar');
    if (oldToolbar) return;

    var toolbar = document.createElement('div');
    toolbar.className = 'widget-toolbar';

    var leftSide = document.createElement('div');
    leftSide.className = 'widget-toolbar-left';
    var leftSpan = document.createElement('span');
    leftSpan.textContent = key ? '🛸 WIDGET: ' + key.toUpperCase() : '🧪 WIDGET TEMPORAL';
    leftSide.appendChild(leftSpan);
    toolbar.appendChild(leftSide);

    if (key) {
        var isCached = stateManager.getCodeCache(key);
        if (!isCached) {
            fetchVersionLabel(key, leftSide);
        }
    }

    var rightSide = document.createElement('div');
    rightSide.className = 'widget-toolbar-right';

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
                stateManager.setState(hashId, null);
                ApiClient.saveWidgetState(SessionContext.getSessionId(), hashId, '{}')
                    .then(function onResetResponse() {
                    var iframe = container.querySelector('iframe');
                    if (iframe) {
                        iframe.srcdoc = buildIframeSrc(id, WidgetManager._registry[id] || code, 'null');
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
    ApiClient.loadWidgetCode(SessionContext.getSessionId(), key)
        .then(function(r) {
            if (!r.ok) throw new Error('not-found');
            return r.json();
        })
        .then(function(data) {
            var vSpan = document.createElement('span');
            vSpan.className = 'widget-v-label';
            vSpan.textContent = '[V' + data.version + ']';
            leftSide.appendChild(vSpan);
        }).catch(function(){});
}
