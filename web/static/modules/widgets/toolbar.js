/**
 * Kairos Widgets — Toolbar
 *
 * UI de toolbar por widget: labels, editar, historial, reset.
 */
window.KairosWidgets = (function(api) {

    // === Toolbar Core ===
    api.createToolbar = function(container, id, key, code, hashId) {
        var oldToolbar = container.querySelector('.widget-toolbar');
        if (oldToolbar) return;

        var toolbar = document.createElement('div');
        toolbar.className = 'widget-toolbar';
        toolbar.style.display = 'flex';
        toolbar.style.justifyContent = 'space-between';
        toolbar.style.alignItems = 'center';
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
            fetchVersionLabel(key, leftSide);
        }

        var rightSide = document.createElement('div');
        rightSide.className = 'widget-toolbar-right';
        rightSide.style.display = 'flex';
        rightSide.style.gap = '8px';

        if (key) {
            var btnEdit = api.createToolbarButton({
                label: 'EDITAR',
                border: '1px solid #00ff99',
                color: '#00ff99',
                onClick: function onEditClick() {
                    api.openEditor(container, id, key, code);
                }
            });
            rightSide.appendChild(btnEdit);

            var btnHist = api.createToolbarButton({
                label: 'HISTORIAL',
                border: '1px solid #00ffff',
                color: '#00ffff',
                onClick: function onHistoryClick() {
                    api.toggleHistoryList(container, id, key);
                }
            });
            rightSide.appendChild(btnHist);
        }

        var btnReset = api.createToolbarButton({
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
                            iframe.srcdoc = api.buildIframeSrc(id, api._registry[id] || code, 'null');
                        }
                    });
                }
            }
        });
        rightSide.appendChild(btnReset);

        toolbar.appendChild(rightSide);
        container.insertBefore(toolbar, container.firstChild);
    };

    function fetchVersionLabel(key, leftSide) {
        fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(key) + '/code')
            .then(function parseVersionResponse(r) { return r.json(); })
            .then(function appendVersionLabel(data) {
                var vSpan = document.createElement('span');
                vSpan.className = 'widget-v-label';
                vSpan.style.color = '#00ffff';
                vSpan.style.marginLeft = '8px';
                vSpan.textContent = '[V' + data.version + ']';
                leftSide.appendChild(vSpan);
            }).catch(function ignoreVersionError(){});
    }

    // === Editor ===
    api.openEditor = function(container, id, key, code) {
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
        textarea.value = api._registry[id] || code;
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

        var btnSave = api.createToolbarButton({
            label: 'GUARDAR VERSIÓN',
            background: '#00ff99',
            color: '#0d1117',
            border: 'none',
            fontWeight: 'bold',
            fontSize: '11px',
            onClick: function onSaveClick() {
                var newCode = textarea.value;
                fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(key) + '/save', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ code: newCode, description: 'Edición manual desde UI' })
                })
                .then(function parseSaveResponse(r) { return r.json(); })
                .then(function onSaveSuccess(data) {
                    api._registry[id] = newCode;
                    container.innerHTML = '';
                    container.dataset.initialized = '';
                    api.createIframe(container, id, newCode);
                }).catch(function onSaveError(err) {
                    console.error("Error saving widget:", err);
                });
            }
        });
        actionsDiv.appendChild(btnSave);

        var btnCancel = api.createToolbarButton({
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
    };

    // === History ===
    api.toggleHistoryList = function(container, id, key) {
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
                                    api._registry[id] = verData.code;
                                    var iframe = container.querySelector('iframe');
                                    if (iframe) {
                                        var hashId = key;
                                        var stateStr = null;
                                        if (window.widgetStates) {
                                            stateStr = window.widgetStates[hashId] || null;
                                        }
                                        var safeStateStr = stateStr !== null ? JSON.stringify(stateStr) : 'null';
                                        iframe.srcdoc = api.buildIframeSrc(id, verData.code, safeStateStr);
                                    }
                                    var label = container.querySelector('.widget-toolbar-left .widget-v-label');
                                    if (label) {
                                        label.textContent = '[V' + v.version + ']';
                                    }
                                    historyDiv.parentNode.removeChild(historyDiv);
                                });
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
    };

    return api;
})(window.KairosWidgets || {});
