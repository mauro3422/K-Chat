/**
 * Kairos Widgets — IFrame Builder
 *
 * Genera el srcdoc HTML inyectado en cada iframe sandboxed.
 * También crea y monta iframes con soporte para widgets oficiales.
 */
import { SessionContext } from '../session-context.js';
import { KairosUtils } from '../utils.js';
import { fnv1a_32, log, KairosWidgets } from './core.js';
import { createToolbar } from './toolbar-core.js';
import stateManager from './state-manager.js';
import { widgetCodeEntryKey } from './contract.js';
import { getInitializedWidgets } from './iframe.js';
import { getLogger } from '../logger.js';
var cbLog = getLogger('iframe-builder');

export function createIframe(container, id, code) {
    if (container.dataset.initialized) return;
    container.dataset.initialized = '1';

    var wm = getInitializedWidgets();
    wm.set(container, { initialized: true, observed: true, widgetId: id });

    var key = container.getAttribute('data-widget-key');
    var hashId = key ? key : 'widget-' + fnv1a_32(code || '');
    var stateStr = stateManager.getState(hashId) || stateManager.getState(id) || null;
    var safeStateStr = stateStr !== null ? JSON.stringify(stateStr) : 'null';

    var placeholder = document.createElement('div');
    placeholder.className = 'widget-placeholder';
    placeholder.innerHTML = '<div class="widget-loading">Cargando widget...</div>';
    container.appendChild(placeholder);

    function mountIframe(widgetCode) {
        if (placeholder && placeholder.parentNode) {
            placeholder.parentNode.removeChild(placeholder);
        }
        createToolbar(container, id, key, widgetCode, hashId);

        var iframe = document.createElement('iframe');
        iframe.className = 'interactive-widget-iframe';
        iframe.sandbox = 'allow-scripts';
        iframe.style = iframe.style || {};
        iframe.style.width = '100%';
        iframe.style.height = '0';
        iframe.style.minHeight = '60px';
        iframe.style.border = 'none';
        iframe.style.background = '#161b22';
        iframe.style.borderRadius = '0 0 8px 8px';
        iframe.style.display = 'block';
        iframe.style.overflow = 'hidden';

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
            KairosWidgets._registry[id] = cachedCode;
            mountIframe(cachedCode);
        } else {
            log(id, 'fetch-init', 'key=' + key);
            var urlBuilder = SessionContext.createSessionUrlBuilder();
            fetch(urlBuilder.widgetCode(key))
                .then(function(r) {
                    if (!r.ok) throw new Error("No encontrado");
                    return r.json();
                })
                .then(function(data) {
                    log(id, 'fetch-ok', 'version=' + data.version + ' code=' + data.code.length + 'b');
                    KairosWidgets._registry[id] = data.code;
                    stateManager.setCodeCache(key, data.code);
                    fetch(urlBuilder.widgetState(widgetCodeEntryKey(key)), {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({ state: data.code })
                    }).catch(function() {});
                    mountIframe(data.code);
                })
                .catch(function(err) {
                    log(id, 'fetch-error', err.message);
                    cbLog.error('fetch_failed', { id: id, key: key, err: err.message });
                    placeholder.innerHTML = '<div class="widget-error" style="color: #ff6b6b; padding: 16px; background: #161b22; border-radius: 8px; border-left: 3px solid #ff6b6b;"><strong>Widget "' + KairosUtils.escHtml(key) + '" no encontrado</strong><br><span style="color: #8b949e; font-size: 13px;">Este widget fue creado en una sesión anterior pero no se guardó oficialmente.<br>Para persistirlo, usá <code>save_widget</code> en el chat.</span></div>';
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
        code + '\n' +
        '<style>\n' +
        'html,body{margin:0;padding:12px;overflow-x:hidden;scrollbar-width:none;}\n' +
        '[style*="100vh"],[style*="100%"],[style*="100VH"],[style*="100Vh"]{height:auto!important;}\n' +
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
