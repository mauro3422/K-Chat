/**
 * Kairos Widgets — IFrame Builder
 *
 * Genera el srcdoc HTML inyectado en cada iframe sandboxed.
 * También crea y monta iframes con soporte para widgets oficiales.
 */
import { ApiClient } from '../api-client.js';
import { SessionContext } from '../session-context.js';
import { Utils } from '../utils.js';
import { fnv1a_32, log, WidgetManager } from './core.js';
import { createToolbar } from './toolbar-core.js';
import stateManager from './state-manager.js';
import { widgetCodeEntryKey } from './contract.js';
import { getInitializedWidgets } from './iframe.js';
import { getLogger } from '../logger.js';
var cbLog = getLogger('iframe-builder');

function createLoadingNode() {
    var node = document.createElement('div');
    node.className = 'widget-loading';
    node.textContent = 'Cargando widget...';
    return node;
}

function createErrorNode(key) {
    var wrap = document.createElement('div');
    wrap.className = 'widget-error';
    wrap.style.color = '#ff6b6b';
    wrap.style.padding = '16px';
    wrap.style.background = '#161b22';
    wrap.style.borderRadius = '8px';
    wrap.style.borderLeft = '3px solid #ff6b6b';

    var strong = document.createElement('strong');
    strong.textContent = 'Widget "' + Utils.escHtml(key) + '" no encontrado';
    wrap.appendChild(strong);
    wrap.appendChild(document.createElement('br'));

    var span = document.createElement('span');
    span.style.color = '#8b949e';
    span.style.fontSize = '13px';
    span.textContent = 'Este widget fue creado en una sesión anterior pero no se guardó oficialmente. Para persistirlo, usá save_widget en el chat.';
    wrap.appendChild(span);

    return wrap;
}

export function createIframe(container, id, code) {
    if (container.dataset.initialized) return;
    container.dataset.initialized = '1';

    var key = container.getAttribute('data-widget-key');

    // Intercept if already pinned to Canvas Workspace
    import('./canvas-workspace.js').then(function(m) {
        if (key && m.CanvasWorkspace.isPinned(key)) {
            container.textContent = '';
            var ph = document.createElement('a');
            ph.href = '#';
            ph.className = 'pinned-widget-placeholder';
            ph.dataset.widgetKey = key;
            ph.innerHTML = `<span class="pin-icon">📌</span> Pinned widget: <strong>${key}</strong> (Ver en Lienzo)`;
            ph.addEventListener('click', (e) => {
                e.preventDefault();
                var card = document.querySelector(`.canvas-card[data-widget-key="${key}"]`);
                if (card) {
                    card.scrollIntoView({ behavior: 'smooth' });
                    card.classList.add('active-drag');
                    setTimeout(() => card.classList.remove('active-drag'), 800);
                }
            });
            container.appendChild(ph);
            return;
        }
        
        // Normal mount flow
        var wm = getInitializedWidgets();
        wm.set(container, { initialized: true, observed: true, widgetId: id });

        var hashId = key ? key : 'widget-' + fnv1a_32(code || '');
        var stateStr = stateManager.getState(hashId) || stateManager.getState(id) || null;
        var safeStateStr = stateStr !== null ? JSON.stringify(stateStr) : 'null';

        var placeholder = document.createElement('div');
        placeholder.className = 'widget-placeholder';
        placeholder.appendChild(createLoadingNode());
        container.appendChild(placeholder);

        function mountIframe(widgetCode) {
            if (placeholder && placeholder.parentNode) {
                placeholder.parentNode.removeChild(placeholder);
            }
            var iframe = document.createElement('iframe');
            iframe.className = 'widget-iframe';
            iframe.sandbox = 'allow-scripts';
            iframe.scrolling = 'no';
            iframe.srcdoc = buildIframeSrc(id, widgetCode, safeStateStr);
            container.appendChild(iframe);
            container.dataset.initialized = '1';
            cbLog.info('mounted', { id: id, key: key, codeLen: widgetCode.length, iframeH: iframe.offsetHeight });
        }

        if (!code && key) {
            // Check session cache first (widget code persisted from previous render)
            var cachedCode = stateManager.getCodeCache(key);
            if (cachedCode) {
                log(id, 'cache-hit', 'key=' + key + ' code=' + cachedCode.length + 'b');
                WidgetManager._registry[id] = cachedCode;
                mountIframe(cachedCode);
            } else {
                log(id, 'fetch-init', 'key=' + key);
                ApiClient.loadWidgetCode(SessionContext.getSessionId(), key)
                    .then(function(r) {
                        if (!r.ok) throw new Error("No encontrado");
                        return r.json();
                    })
                    .then(function(data) {
                        log(id, 'fetch-ok', 'version=' + data.version + ' code=' + data.code.length + 'b');
                        WidgetManager._registry[id] = data.code;
                        stateManager.setCodeCache(key, data.code);
                        ApiClient.saveWidgetState(SessionContext.getSessionId(), widgetCodeEntryKey(key), data.code)
                            .catch(function() {});
                        mountIframe(data.code);
                    })
                    .catch(function(err) {
                        log(id, 'fetch-error', err.message);
                        cbLog.error('fetch_failed', { id: id, key: key, err: err.message });
                        if (placeholder.firstChild) {
                            placeholder.removeChild(placeholder.firstChild);
                        }
                        placeholder.appendChild(createErrorNode(key));
                    });
            }
        } else {
            mountIframe(code);
        }
    });

    if (!code && key) {
        // Check session cache first (widget code persisted from previous render)
        var cachedCode = stateManager.getCodeCache(key);
        if (cachedCode) {
            log(id, 'cache-hit', 'key=' + key + ' code=' + cachedCode.length + 'b');
            WidgetManager._registry[id] = cachedCode;
            mountIframe(cachedCode);
        } else {
            log(id, 'fetch-init', 'key=' + key);
            ApiClient.loadWidgetCode(SessionContext.getSessionId(), key)
                .then(function(r) {
                    if (!r.ok) throw new Error("No encontrado");
                    return r.json();
                })
                .then(function(data) {
                    log(id, 'fetch-ok', 'version=' + data.version + ' code=' + data.code.length + 'b');
                    WidgetManager._registry[id] = data.code;
                    stateManager.setCodeCache(key, data.code);
                    ApiClient.saveWidgetState(SessionContext.getSessionId(), widgetCodeEntryKey(key), data.code)
                        .catch(function() {});
                    mountIframe(data.code);
                })
                .catch(function(err) {
                    log(id, 'fetch-error', err.message);
                    cbLog.error('fetch_failed', { id: id, key: key, err: err.message });
                    if (placeholder.firstChild) {
                        placeholder.removeChild(placeholder.firstChild);
                    }
                    placeholder.appendChild(createErrorNode(key));
                });
        }
    } else {
        mountIframe(code);
    }

    var parentScroll = container.parentElement
        ? (container.parentElement.scrollHeight > container.parentElement.clientHeight ? 'SCROLL' : 'no-scroll')
        : '?';
    log(id, 'montado', 'padre-scroll=' + parentScroll + ' contenedor-h=' + container.offsetHeight + 'px');
}

export function buildIframeSrc(id, code, stateStr) {
    var safeCode = code.replace(/<\/script>/gi, '<\\/script>');
    return '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n' +
        '<style>\n' +
        'body { margin:0; padding:12px; font-family:system-ui,-apple-system,sans-serif; color:#c9d1d9; background:#161b22; }\n' +
        'input,button,select,textarea { font-family:inherit; color-scheme:dark; }\n' +
        '</style>\n</head>\n<body>\n' +
        '<script>\n' +
        'var _origin=window.location.origin==="null"?"*":window.location.origin;\n' +
        'window.onerror=function(msg,url,line,col,err){window.parent.postMessage({type:"widget-error",id:"' + id + '",message:msg,line:line,col:col},_origin);};\n' +
        'window.initialState=JSON.parse(' + stateStr + ');\n' +
        'window.saveState=function(stateObj){window.parent.postMessage({type:"save-widget-state",id:"' + id + '",state:typeof stateObj==="string"?stateObj:JSON.stringify(stateObj)},_origin);};\n' +
        '</' + 'script>\n' +
        safeCode + '\n' +
        '<style>\n' +
        'html,body{margin:0;padding:12px;overflow:hidden;scrollbar-width:none;box-sizing:border-box;width:100%;}\n' +
        'html::-webkit-scrollbar,body::-webkit-scrollbar{display:none;}\n' +
        '</style>\n' +
        '<script>\n' +
        'var _lastSentH=0;\n' +
        'function getDocHeight(){return Math.max(document.documentElement.scrollHeight,document.documentElement.offsetHeight,document.body.scrollHeight,document.body.offsetHeight);}\n' +
        'function sendHeight(){var h=Math.max(1,Math.round(getDocHeight()));if(Math.abs(h-_lastSentH)<=2)return;_lastSentH=h;window.parent.postMessage({type:"resize-iframe",id:"' + id + '",height:h},_origin);}\n' +
        'sendHeight();setTimeout(sendHeight,100);setTimeout(sendHeight,600);setTimeout(sendHeight,2000);\n' +
        'window.addEventListener("load",function(){sendHeight();requestAnimationFrame(function(){requestAnimationFrame(function(){requestAnimationFrame(sendHeight);});});});\n' +
        'if(window.ResizeObserver){var _ro=new ResizeObserver(sendHeight);_ro.observe(document.documentElement);_ro.observe(document.body);}\n' +
        '</' + 'script>\n' +
        '</body>\n</html>';
}
