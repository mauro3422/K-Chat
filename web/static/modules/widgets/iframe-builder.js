/**
 * Kairos Widgets — IFrame Builder
 *
 * Genera el srcdoc HTML inyectado en cada iframe sandboxed.
 * También crea y monta iframes con soporte para widgets oficiales.
 */
window.KairosWidgets = (function(api) {
    api.createIframe = function(container, id, code) {
        if (container.dataset.initialized) return;
        container.dataset.initialized = '1';

        var key = container.getAttribute('data-widget-key');
        var hashId = key ? key : 'widget-' + api.fnv1a_32(code || '');
        var stateStr = null;
        if (window.widgetStates) {
            stateStr = window.widgetStates[hashId] || window.widgetStates[id] || null;
        }
        var safeStateStr = stateStr !== null ? JSON.stringify(stateStr) : 'null';

        var placeholder = document.createElement('div');
        placeholder.className = 'widget-placeholder';
        placeholder.innerHTML = '<div class="widget-loading">Cargando widget...</div>';
        container.appendChild(placeholder);

        function mountIframe(widgetCode) {
            if (placeholder && placeholder.parentNode) {
                placeholder.parentNode.removeChild(placeholder);
            }
            api.createToolbar(container, id, key, widgetCode, hashId);

            var iframe = document.createElement('iframe');
            iframe.className = 'interactive-widget-iframe';
            iframe.sandbox = 'allow-scripts';
            iframe.scrolling = 'no';
            iframe.style.width = '100%';
            iframe.style.height = '200px';
            iframe.style.minHeight = '200px';
            iframe.style.border = 'none';
            iframe.style.background = '#161b22';
            iframe.style.borderRadius = '0 0 8px 8px';
            iframe.style.display = 'block';
            iframe.style.overflow = 'hidden';

            iframe.srcdoc = api.buildIframeSrc(id, widgetCode, safeStateStr);
            container.appendChild(iframe);
            container.dataset.initialized = '1';
        }

        if (!code && key) {
            api.log(id, 'fetch-init', 'key=' + key);
            fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(key) + '/code')
                .then(function(r) {
                    if (!r.ok) throw new Error("No encontrado");
                    return r.json();
                })
                .then(function(data) {
                    api.log(id, 'fetch-ok', 'version=' + data.version + ' code=' + data.code.length + 'b');
                    api._registry[id] = data.code;
                    mountIframe(data.code);
                })
                .catch(function(err) {
                    api.log(id, 'fetch-error', err.message);
                    placeholder.innerHTML = '<div class="widget-error" style="color: #ff3366; padding: 12px; background: #161b22; border-radius: 8px;">Error cargando widget oficial "' + KairosUtils.escHtml(key) + '": ' + KairosUtils.escHtml(err.message) + '</div>';
                });
        } else {
            mountIframe(code);
        }

        var parentScroll = container.parentElement
            ? (container.parentElement.scrollHeight > container.parentElement.clientHeight ? 'SCROLL' : 'no-scroll')
            : '?';
        api.log(id, 'montado', 'padre-scroll=' + parentScroll + ' contenedor-h=' + container.offsetHeight + 'px');
    };

    api.buildIframeSrc = function(id, code, stateStr) {
        return '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n' +
            '<style>\n' +
            'body { margin:0; padding:12px; font-family:system-ui,-apple-system,sans-serif; color:#c9d1d9; background:#161b22; }\n' +
            'input,button,select,textarea { font-family:inherit; color-scheme:dark; }\n' +
            '</style>\n</head>\n<body>\n' +
            '<script>\n' +
            'var _origin=window.location.origin;\n' +
            'window.onerror=function(msg,url,line,col,err){window.parent.postMessage({type:"widget-error",id:"' + id + '",message:msg,line:line,col:col},_origin);};\n' +
            'window.initialState=JSON.parse(' + stateStr + ');\n' +
            'window.saveState=function(stateObj){window.parent.postMessage({type:"save-widget-state",id:"' + id + '",state:typeof stateObj==="string"?stateObj:JSON.stringify(stateObj)},_origin);};\n' +
            '</' + 'script>\n' +
            code + '\n' +
            '<style>\n' +
            'html,body{height:auto!important;min-height:auto!important;overflow:visible!important;margin:0;padding:12px;overflow-x:hidden;scrollbar-width:none;}\n' +
            '[style*="100vh"],[style*="100%"],[style*="100VH"],[style*="100Vh"]{height:auto!important;}\n' +
            'html::-webkit-scrollbar,body::-webkit-scrollbar{display:none;}\n' +
            '</style>\n' +
            '<script>\n' +
            'var _lastSentH=0;\n' +
            'function sendHeight(){var h=Math.max(1,Math.round(document.body.scrollHeight));if(Math.abs(h-_lastSentH)<=2)return;_lastSentH=h;window.parent.postMessage({type:"resize-iframe",id:"' + id + '",height:h},_origin);}\n' +
            'sendHeight();setTimeout(sendHeight,100);setTimeout(sendHeight,600);setTimeout(sendHeight,2000);\n' +
            'window.addEventListener("load",function(){sendHeight();requestAnimationFrame(function(){requestAnimationFrame(sendHeight);});});\n' +
            'if(window.ResizeObserver){new ResizeObserver(sendHeight).observe(document.body);}\n' +
            '</' + 'script>\n' +
            '</body>\n</html>';
    };

    return api;
})(window.KairosWidgets || {});
