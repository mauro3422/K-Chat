/**
 * Kairos Widgets — Toolbar Editor
 *
 * Editor inline de código: apertura, guardado, cancelación y validación.
 */
import { ApiClient } from '../api-client.js';
import { SessionContext } from '../session-context.js';
import { createToolbarButton } from './ui-helpers.js';
import { createIframe } from './iframe-builder.js';
import { KairosWidgets } from './core.js';

function clearContainer(container) {
    if (container && typeof container.replaceChildren === 'function') {
        container.replaceChildren();
        return;
    }
    if (container) {
        container.textContent = '';
    }
}

export function openEditor(container, id, key, code) {
    var iframe = container.querySelector('iframe');
    if (iframe) iframe.style.display = 'none';

    var toolbarRight = container.querySelector('.widget-toolbar-right');
    if (toolbarRight) toolbarRight.style.display = 'none';

    var editorDiv = document.createElement('div');
    editorDiv.className = 'widget-editor-container';

    var textarea = document.createElement('textarea');
    textarea.className = 'widget-editor-textarea';
    textarea.value = KairosWidgets._registry[id] || code;
    editorDiv.appendChild(textarea);

    var actionsDiv = document.createElement('div');
    actionsDiv.className = 'widget-editor-actions';

    var btnSave = createToolbarButton({
        label: 'GUARDAR VERSIÓN',
        background: '#00ff99',
        color: '#0d1117',
        border: 'none',
        fontWeight: 'bold',
        fontSize: '11px',
        onClick: function onSaveClick() {
            var newCode = textarea.value;
            ApiClient.saveWidgetCode(SessionContext.getSessionId(), key, newCode, 'Edición manual desde UI')
            .then(function parseSaveResponse(r) { return r.json(); })
            .then(function onSaveSuccess(data) {
                KairosWidgets._registry[id] = newCode;
                clearContainer(container);
                container.dataset.initialized = '';
                createIframe(container, id, newCode);
            }).catch(function onSaveError(err) {
                console.error("Error saving widget:", err);
            });
        }
    });
    actionsDiv.appendChild(btnSave);

    var btnCancel = createToolbarButton({
        label: 'CANCELAR',
        border: '1px solid #30363d',
        color: '#8b949e',
        onClick: function onCancelClick() {
            editorDiv.parentNode.removeChild(editorDiv);
            if (iframe) iframe.style.display = 'block';
            if (toolbarRight) toolbarRight.style.display = 'flex';
        }
    });
    actionsDiv.appendChild(btnCancel);

    editorDiv.appendChild(actionsDiv);
    container.appendChild(editorDiv);
}
