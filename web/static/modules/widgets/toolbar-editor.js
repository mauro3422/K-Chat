/**
 * Kairos Widgets — Toolbar Editor
 *
 * Editor inline de código: apertura, guardado, cancelación y validación.
 */
import { SessionContext } from '../session-context.js';
import { createToolbarButton } from './ui-helpers.js';
import { createIframe } from './iframe-builder.js';
import { KairosWidgets } from './core.js';

export function openEditor(container, id, key, code) {
    var urlBuilder = SessionContext.createSessionUrlBuilder();
    var iframe = container.querySelector('iframe');
    if (iframe) iframe.style.display = 'none';

    var toolbarRight = container.querySelector('.widget-toolbar-right');
    if (toolbarRight) toolbarRight.style.display = 'none';

    var editorDiv = document.createElement('div');
    editorDiv.className = 'widget-editor-container';
    editorDiv.style.padding = '8px';
    editorDiv.style.background = '#161b22';
    editorDiv.style.border = '1px solid #30363d';
    editorDiv.style.borderRadius = '0 0 8px 8px';

    var textarea = document.createElement('textarea');
    textarea.value = KairosWidgets._registry[id] || code;
    textarea.style.width = '100%';
    textarea.style.height = '300px';
    textarea.style.background = '#0d1117';
    textarea.style.color = '#00ff99';
    textarea.style.fontFamily = 'monospace';
    textarea.style.fontSize = '12px';
    textarea.style.border = '1px solid #00ff99';
    textarea.style.borderRadius = '4px';
    textarea.style.padding = '8px';
    textarea.style.boxSizing = 'border-box';
    editorDiv.appendChild(textarea);

    var actionsDiv = document.createElement('div');
    actionsDiv.style.display = 'flex';
    actionsDiv.style.justifyContent = 'flex-end';
    actionsDiv.style.gap = '8px';
    actionsDiv.style.marginTop = '8px';

    var btnSave = createToolbarButton({
        label: 'GUARDAR VERSIÓN',
        background: '#00ff99',
        color: '#0d1117',
        border: 'none',
        fontWeight: 'bold',
        fontSize: '11px',
        onClick: function onSaveClick() {
            var newCode = textarea.value;
            fetch(urlBuilder.widgetSave(key), {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ code: newCode, description: 'Edición manual desde UI' })
            })
            .then(function parseSaveResponse(r) { return r.json(); })
            .then(function onSaveSuccess(data) {
                KairosWidgets._registry[id] = newCode;
                container.innerHTML = '';
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
