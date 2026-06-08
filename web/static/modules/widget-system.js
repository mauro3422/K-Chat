/**
 * widget-system.js — Sistema modular de widgets interactivos
 *
 * Maneja: extracción de bloques html-widget del markdown,
 * creación de iframes sandboxed, comunicación iframe↔padre,
 * persistencia de estado, y debug.
 *
 * Interfaz pública: window.KairosWidgets
 */
var KairosWidgets = (function() {
  var registry = {};
  var debug = {};
  var index = 0;

  function log(id, label, detail) {
    debug[id] = debug[id] || { events: [] };
    debug[id].events.push({
      t: Date.now(),
      label: label,
      detail: String(detail || '').substring(0, 200)
    });
    try { logUI('[W] ' + id, label + ' ' + String(detail || '').substring(0, 120)); } catch(e) {}
  }

  function extract(text) {
    var widgetRegex = /```html-widget\s*\n([\s\S]*?)\n```/g;
    return text.replace(widgetRegex, function(match, code) {
      var id = 'widget-' + index++;
      code = code.replace(/\?\.([\w.]+)\s*=(?!=)/g, '.$1 =');
      registry[id] = code;
      return '<div class="interactive-widget-container" data-widget-id="' + id + '"></div>';
    });
  }

  function buildIframeSrc(id, code, stateStr) {
    return '<!DOCTYPE html>\n<html>\n<head>\n<meta charset="utf-8">\n' +
      '<style>\n' +
      'body { margin:0; padding:12px; font-family:system-ui,-apple-system,sans-serif; color:#c9d1d9; background:#161b22; }\n' +
      'input,button,select,textarea { font-family:inherit; color-scheme:dark; }\n' +
      '</style>\n</head>\n<body>\n' +
      '<script>\n' +
      'window.onerror=function(msg,url,line,col,err){window.parent.postMessage({type:"widget-error",id:"' + id + '",message:msg,line:line,col:col},"*");};\n' +
      'window.initialState=JSON.parse(' + stateStr + ');\n' +
      'window.saveState=function(stateObj){window.parent.postMessage({type:"save-widget-state",id:"' + id + '",state:typeof stateObj==="string"?stateObj:JSON.stringify(stateObj)},"*");};\n' +
      '</' + 'script>\n' +
      code + '\n' +
      '<style>\n' +
      'html,body{height:auto!important;min-height:auto!important;overflow:visible!important;margin:0;padding:12px;overflow-x:hidden;scrollbar-width:none;}\n' +
      '[style*="100vh"],[style*="100%"],[style*="100VH"],[style*="100Vh"]{height:auto!important;}\n' +
      'html::-webkit-scrollbar,body::-webkit-scrollbar{display:none;}\n' +
      '</style>\n' +
      '<script>\n' +
      'var _lastSentH=0;\n' +
      'function sendHeight(){var h=Math.max(1,Math.round(document.body.scrollHeight));if(Math.abs(h-_lastSentH)<=2)return;_lastSentH=h;window.parent.postMessage({type:"resize-iframe",id:"' + id + '",height:h},"*");}\n' +
      'sendHeight();setTimeout(sendHeight,100);setTimeout(sendHeight,600);setTimeout(sendHeight,2000);\n' +
      'window.addEventListener("load",function(){sendHeight();requestAnimationFrame(function(){requestAnimationFrame(sendHeight);});});\n' +
      'if(window.ResizeObserver){new ResizeObserver(sendHeight).observe(document.body);}\n' +
      '</' + 'script>\n' +
      '</body>\n</html>';
  }

  var widgetObserver = null;

  function createIframe(container, id, code) {
    var stateStr = window.widgetStates && window.widgetStates[id] ? window.widgetStates[id] : null;
    var safeStateStr = stateStr !== null ? JSON.stringify(stateStr) : 'null';

    // Agregar placeholder visual mientras carga
    var placeholder = document.createElement('div');
    placeholder.className = 'widget-placeholder';
    placeholder.innerHTML = '<div class="widget-loading">Cargando widget...</div>';
    container.appendChild(placeholder);

    var iframe = document.createElement('iframe');
    iframe.className = 'interactive-widget-iframe';
    iframe.sandbox = 'allow-scripts';
    iframe.scrolling = 'no';
    iframe.style.width = '100%';
    iframe.style.height = '200px'; // Altura mínima mientras carga
    iframe.style.minHeight = '200px';
    iframe.style.border = 'none';
    iframe.style.background = '#161b22';
    iframe.style.borderRadius = '8px';
    iframe.style.marginTop = '8px';
    iframe.style.display = 'block';
    iframe.style.overflow = 'hidden';

    iframe.srcdoc = buildIframeSrc(id, code, safeStateStr);
    
    // Remover placeholder cuando el iframe cargue
    iframe.onload = function() {
      if (placeholder && placeholder.parentNode) {
        placeholder.parentNode.removeChild(placeholder);
      }
    };
    
    container.appendChild(iframe);
    container.dataset.initialized = '1';

    var parentScroll = container.parentElement
      ? (container.parentElement.scrollHeight > container.parentElement.clientHeight ? 'SCROLL' : 'no-scroll')
      : '?';
    log(id, 'montado', 'padre-scroll=' + parentScroll + ' contenedor-h=' + container.offsetHeight + 'px');
  }

  function initAll(parentEl, forceImmediate) {
    parentEl.querySelectorAll('.interactive-widget-container').forEach(function(container) {
      if (container.dataset.initialized) return;
      var id = container.getAttribute('data-widget-id');
      var code = registry[id];
      if (!code) return;

      log(id, 'init', 'code=' + code.length + 'b padre=' + (parentEl.className || parentEl.id || '?'));

      // Si forceImmediate es true, o no hay observer, crear iframe inmediatamente
      if (forceImmediate || !widgetObserver) {
        createIframe(container, id, code);
      } else {
        widgetObserver.observe(container);
        log(id, 'lazy-queue', 'esperando visibilidad');
      }
    });
  }

  function startMessageHandler() {
    if (window.IntersectionObserver) {
      widgetObserver = new IntersectionObserver(function(entries) {
        entries.forEach(function(entry) {
          if (entry.isIntersecting) {
            var container = entry.target;
            var id = container.getAttribute('data-widget-id');
            var code = registry[id];
            if (code && !container.dataset.initialized) {
              log(id, 'lazy-load', 'visible en viewport');
              createIframe(container, id, code);
            }
            widgetObserver.unobserve(container);
          }
        });
      }, { rootMargin: '100px' });
    }

    window.addEventListener('message', function(event) {
      if (!event.data) return;

      if (event.data.type === 'resize-iframe') {
        var iframe = document.querySelector('[data-widget-id="' + event.data.id + '"] iframe');
        if (iframe) {
          iframe.style.height = (event.data.height + 4) + 'px';
          log(event.data.id, 'altura', event.data.height + 'px -> ' + (event.data.height + 4) + 'px');
        }
      } else if (event.data.type === 'save-widget-state') {
        window.widgetStates = window.widgetStates || {};
        window.widgetStates[event.data.id] = event.data.state;
        fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(event.data.id) + '/state', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ state: event.data.state })
        });
      } else if (event.data.type === 'widget-error') {
        console.error('[Widget ' + event.data.id + '] ' + event.data.message + ' (linea ' + event.data.line + ')');
        log(event.data.id, 'ERROR', event.data.message + ' L:' + event.data.line);
      }
    });
  }

  function reset() {
    registry = {};
    index = 0;
    log('system', 'reset', 'registro de widgets y contador reseteados');
  }

  return {
    extract: extract,
    initAll: initAll,
    log: log,
    reset: reset,
    startMessageHandler: startMessageHandler,
    buildIframeSrc: buildIframeSrc,
    get registry() { return registry; },
    get debug() { return debug; },
    get index() { return index; }
  };
})();
