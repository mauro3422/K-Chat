var lastUserMessageText = '';
window.widgetStates = window.widgetStates || {};

window.retryLastMessage = function() {
  var lastAsstMsg = document.querySelector('.msg.assistant:last-child');
  if (lastAsstMsg && lastAsstMsg.querySelector('.error-card')) {
    lastAsstMsg.remove();
  }
  var input = document.getElementById('msg-input');
  if (input) {
    input.value = lastUserMessageText;
    var form = document.getElementById('chat-form');
    if (form) {
      // Forzar el submit del formulario de forma programática
      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    }
  }
};

// Despachador de Eventos para el flujo de streaming
class StreamEventDispatcher {
  constructor() {
    this.listeners = {};
  }

  on(event, cb) {
    if (!this.listeners[event]) {
      this.listeners[event] = [];
    }
    this.listeners[event].push(cb);
  }

  emit(event, data, state) {
    var list = this.listeners[event] || [];
    for (var i = 0; i < list.length; i++) {
      try {
        list[i](data, state);
      } catch (e) {
        console.error("Error in listener for " + event + ":", e);
      }
    }
  }
}

// Inicializar el despachador global
var streamDispatcher = new StreamEventDispatcher();

// Conector de Razonamiento
streamDispatcher.on('reasoning', function(token, state) {
  state.reasoningText += token;
  var toolCount = state.asstDiv.querySelectorAll('.tool-calls').length;
  if (state.reasoningEls.length <= toolCount) {
    if (state.reasoningEls.length > 0) {
      var prev = state.reasoningEls[state.reasoningEls.length - 1];
      prev.querySelector('summary').textContent = 'Razonamiento';
      prev.open = false;

      var newDet = document.createElement('details');
      newDet.className = 'reasoning';
      newDet.open = true;
      newDet.innerHTML = '<summary>Razonando...</summary><div class="rt"></div>';
      state.asstDiv.appendChild(newDet);
      state.reasoningEls.push(newDet);
      logUI('reasoning_phase', state.reasoningEls.length);
    } else {
      var newDet = document.createElement('details');
      newDet.className = 'reasoning';
      newDet.open = true;
      newDet.innerHTML = '<summary>Razonando...</summary><div class="rt"></div>';
      state.bodyDivs[0].insertAdjacentElement('beforebegin', newDet);
      state.reasoningEls.push(newDet);
      logUI('reasoning_phase', state.reasoningEls.length);
    }
  }
  var rt = state.reasoningEls[state.reasoningEls.length - 1].querySelector('.rt');
  if (rt) rt.textContent += token;
});

// Conector de Contenido
streamDispatcher.on('content', function(token, state) {
  var phaseIdx = Math.max(0, state.reasoningEls.length - 1);
  while (state.bodyDivs.length <= phaseIdx) {
    var newBody = document.createElement('div');
    newBody.className = 'msg-body md-content';

    var lastDet = state.reasoningEls[state.reasoningEls.length - 1];
    var nextEl = lastDet ? lastDet.nextSibling : null;
    if (nextEl && nextEl.classList && nextEl.classList.contains('tool-calls')) {
      nextEl.insertAdjacentElement('afterend', newBody);
    } else if (lastDet) {
      lastDet.insertAdjacentElement('afterend', newBody);
    } else {
      state.asstDiv.appendChild(newBody);
    }
    state.bodyDivs.push(newBody);
    state.contentTexts.push('');
  }
  if (!state.contentTexts[phaseIdx]) logUI('body_start', token.substring(0, 60));
  state.contentTexts[phaseIdx] += token;
  state.bodyDivs[phaseIdx].innerHTML = DOMPurify.sanitize(parseMarkdown(state.contentTexts[phaseIdx]));
  initWidgets(state.bodyDivs[phaseIdx]);
});

// Conector de Llamadas de Herramientas (Tool Calls)
streamDispatcher.on('tool_call', function(dataStr, state) {
  var info = JSON.parse(dataStr);
  if (info.status === 'partial') return;

  var allTc = state.asstDiv.querySelectorAll('.tool-calls');
  var tcEl = null;

  if (info.status === 'calling') {
    var foundIn = null;
    for (var ti = 0; ti < allTc.length; ti++) {
      if (allTc[ti].querySelector('[data-id="' + info.id + '"]')) {
        foundIn = allTc[ti]; break;
      }
    }
    if (foundIn) {
      tcEl = foundIn;
    } else if (allTc.length < state.reasoningEls.length) {
      tcEl = document.createElement('div');
      tcEl.className = 'tool-calls';
      var lastDet = state.reasoningEls[state.reasoningEls.length - 1];
      lastDet.insertAdjacentElement('afterend', tcEl);
      logUI('tool_calls_seq', state.reasoningEls.length);
    } else if (allTc.length > 0) {
      tcEl = allTc[allTc.length - 1];
    } else {
      tcEl = document.createElement('div');
      tcEl.className = 'tool-calls';
      state.bodyDivs[0].insertAdjacentElement('beforebegin', tcEl);
      logUI('tool_calls_seq', 0);
    }
  } else {
    for (var ti2 = 0; ti2 < allTc.length; ti2++) {
      if (allTc[ti2].querySelector('[data-id="' + info.id + '"]')) {
        tcEl = allTc[ti2]; break;
      }
    }
    if (!tcEl && allTc.length > 0) tcEl = allTc[allTc.length - 1];
  }

  if (!tcEl) return;

  var existing = tcEl.querySelector('[data-id="' + info.id + '"]');
  if (info.status === 'calling') {
    if (!existing) {
      var span = document.createElement('span');
      span.className = 'tc-item calling';
      span.setAttribute('data-id', info.id);
      span.setAttribute('data-tool', info.name);
      span.innerHTML = '<span class="tc-spinner"></span> ' + escHtml(info.name);
      tcEl.appendChild(span);
      logUI('tool_calling', info.name);
    }
  } else {
    if (existing) {
      existing.className = 'tc-item ' + info.status;
      existing.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + info.name;
      logUI('tool_' + info.status, info.name);
    } else {
      var span2 = document.createElement('span');
      span2.className = 'tc-item ' + info.status;
      span2.setAttribute('data-id', info.id);
      span2.innerHTML = (info.status === 'ok' ? '&#10003; ' : '&#10007; ') + (info.name || '?');
      tcEl.appendChild(span2);
      logUI('tool_' + info.status, info.name);
    }
  }
});

// Registrar logStream para telemetría
streamDispatcher.on('reasoning', function(token) { logStream('reasoning', token); });
streamDispatcher.on('content', function(token) { logStream('content', token); });
streamDispatcher.on('tool_call', function(dataStr) { logStream('tool_call', dataStr); });

// Manejo del envío del formulario de chat
document.addEventListener('submit', function(e) {
  var form = e.target;
  if (form.id !== 'chat-form') return;
  e.preventDefault();

  var input = document.getElementById('msg-input');
  if (!input) input = form.querySelector('input[name="message"]');
  if (!input) return;
  var text = input.value.trim();
  if (!text) return;

  lastUserMessageText = text;

  var oldUrl = window.location.pathname;
  if (oldUrl === '/') { window.history.replaceState({sid:sessionId}, '', '/sessions/' + sessionId); }

  input.disabled = true;
  document.getElementById('spinner').textContent = '...';

  document.getElementById('messages').insertAdjacentHTML('beforeend',
    '<div class="msg user"><div class="msg-label">Tu</div><div class="msg-body">' + text.replace(/</g,'&lt;').replace(/>/g,'&gt;') + '</div></div>');
  var asstDiv = document.createElement('div');
  asstDiv.className = 'msg assistant';
  asstDiv.innerHTML = '<div class="msg-label">Kairos</div><div class="msg-body md-content">Pensando...</div>';
  document.getElementById('messages').appendChild(asstDiv);
  esc();

  (async function() {
      var buf = '';

      // Crear objeto de estado del streaming para este ciclo
      var state = {
        asstDiv: asstDiv,
        bodyDivs: [asstDiv.querySelector('.msg-body')],
        reasoningEls: [],
        contentTexts: [''],
        reasoningText: '',
        firstToken: true
      };

      try {
        var resp = await fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(defaultModel), {
          method: 'POST',
          headers: {'Content-Type': 'application/x-www-form-urlencoded'},
          body: 'message=' + encodeURIComponent(text)
        });
        var reader = resp.body.getReader();
        var decoder = new TextDecoder();

        while (true) {
          var r = await reader.read();
          if (r.done) break;
          buf += decoder.decode(r.value);
          var lines = buf.split('\n');
          buf = lines.pop();
          for (var line of lines) {
            if (!line.trim()) continue;
            try { var msg = JSON.parse(line); } catch(e) { continue; }
            
            // Acción ejecutada al recibir el primer token de la respuesta
            if (state.firstToken) {
              state.bodyDivs[0].textContent = '';
              state.firstToken = false;
              logUI('pensando_cleared', '' + msg.t);
            }
            
            // Despachar el evento a través del despachador
            streamDispatcher.emit(msg.t, msg.d, state);
          }
        }

        // Limpiar cualquier tool que haya quedado colgada en 'calling'
        var callingPills = asstDiv.querySelectorAll('.tc-item.calling');
        callingPills.forEach(function(pill) {
          pill.className = 'tc-item error';
          var toolName = pill.getAttribute('data-tool') || 'tool';
          pill.innerHTML = '&#10007; ' + escHtml(toolName);
          logUI('tool_error', toolName);
        });

        // Finalización del streaming
        if (state.reasoningEls.length) {
          state.reasoningEls[state.reasoningEls.length - 1].querySelector('summary').textContent = 'Razonamiento';
          logUI('reasoning_done', state.reasoningEls.length + ' fases');
        }

        // Renderizado final de todos los bloques markdown
        for (var idx = 0; idx < state.contentTexts.length; idx++) {
          if (state.contentTexts[idx]) {
            state.bodyDivs[idx].innerHTML = DOMPurify.sanitize(parseMarkdown(state.contentTexts[idx]));
            initWidgets(state.bodyDivs[idx]);
          }
        }

        refreshSidebar();
        if (typeof debugVisible !== 'undefined' && debugVisible) refreshDebug();
      } catch(e2) {
        // Marcar todas las pills de tools en estado 'calling' como 'error'
        var callingPills = asstDiv.querySelectorAll('.tc-item.calling');
        callingPills.forEach(function(pill) {
          pill.className = 'tc-item error';
          var toolName = pill.getAttribute('data-tool') || 'tool';
          pill.innerHTML = '&#10007; ' + escHtml(toolName);
          logUI('tool_error', toolName);
        });

        var bodyDiv = asstDiv.querySelector('.msg-body');
        if (bodyDiv) {
          bodyDiv.innerHTML = 
            '<div class="error-card">' +
              '<div class="error-header">&#9888; Error de Conexión</div>' +
              '<div class="error-detail">No se pudo recibir la respuesta del asistente. Detalle: ' + escHtml(e2.toString()) + '</div>' +
              '<button class="error-retry-btn" onclick="retryLastMessage()">Reintentar envío</button>' +
            '</div>';
        } else {
          asstDiv.querySelector('.msg-body').textContent = 'Error: ' + e2;
        }
      }
    input.disabled = false;
    input.value = '';
    document.getElementById('spinner').textContent = '';
    input.focus();
    esc();
  })();
});

var widgetRegistry = {};

function parseMarkdown(text) {
  if (typeof marked === 'undefined') return text;
  
  var cleanText = text;
  
  // Buscar bloques ```html-widget ... ``` cerrados
  var widgetRegex = /```html-widget\s*\n([\s\S]*?)\n```/g;
  var widgetIndex = 0;
  
  cleanText = cleanText.replace(widgetRegex, function(match, code) {
    var id = 'widget-' + widgetIndex++;
    widgetRegistry[id] = code;
    return '<div class="interactive-widget-container" data-widget-id="' + id + '"></div>';
  });
  
  // Preprocesar tablas que usan '+' en sus separadores (ej. |---+---+---|)
  cleanText = cleanText.replace(/^([ \t]*\|[ \t]*[:\-\+\| \t]+)$/gm, function(match) {
    return match.replace(/\+/g, '-');
  });
  // Preprocesar notas al pie (Footnotes)
  // Referencias: [^1]
  cleanText = cleanText.replace(/\[\^([^\]]+)\](?!\:)/g, '<sup><a href="#fn-$1" id="fnref-$1" class="fn-ref">$1</a></sup>');
  // Definiciones: [^1]: texto
  cleanText = cleanText.replace(/^\[\^([^\]]+)\]:\s*(.*)$/gm, '<div class="footnote-def" id="fn-$1"><a href="#fnref-$1" class="fn-back">↩</a> <strong>$1:</strong> $2</div>');
  return marked.parse(cleanText);
}

function initWidgets(parentEl) {
  parentEl.querySelectorAll('.interactive-widget-container').forEach(function(container) {
    if (container.dataset.initialized) return;
    var id = container.getAttribute('data-widget-id');
    var code = widgetRegistry[id];
    if (!code) return;
    
    var stateStr = window.widgetStates && window.widgetStates[id] ? window.widgetStates[id] : '{}';
    var safeStateStr = JSON.stringify(stateStr);
    
    var iframe = document.createElement('iframe');
    iframe.className = 'interactive-widget-iframe';
    iframe.sandbox = 'allow-scripts';
    iframe.style.width = '100%';
    iframe.style.height = '150px';
    iframe.style.border = 'none';
    iframe.style.background = '#161b22';
    iframe.style.borderRadius = '8px';
    iframe.style.marginTop = '8px';
    iframe.style.display = 'block';
    
    var docContent = `
      <!DOCTYPE html>
      <html>
      <head>
        <meta charset="utf-8">
        <style>
          body {
            margin: 0;
            padding: 12px;
            font-family: system-ui, -apple-system, sans-serif;
            color: #c9d1d9;
            background: #161b22;
          }
          input, button, select, textarea {
            font-family: inherit;
            color-scheme: dark;
          }
        </style>
      </head>
      <body>
        <script>
          window.initialState = JSON.parse(${safeStateStr});
          window.saveState = function(stateObj) {
            window.parent.postMessage({
              type: 'save-widget-state',
              id: '${id}',
              state: typeof stateObj === 'string' ? stateObj : JSON.stringify(stateObj)
            }, '*');
          };
        </script>
        ${code}
        <style>
          /* Evitar bucles de redimensionamiento si el modelo define height: 100vh o min-height */
          html, body {
            height: auto !important;
            min-height: auto !important;
            background: transparent !important;
          }
        </style>
        <script>
          function sendHeight() {
            var height = document.documentElement.scrollHeight;
            window.parent.postMessage({ type: 'resize-iframe', id: '${id}', height: height }, '*');
          }
          window.addEventListener('load', sendHeight);
          if (window.ResizeObserver) {
            new ResizeObserver(sendHeight).observe(document.body);
          }
          document.addEventListener('click', sendHeight);
        </script>
      </body>
      </html>
    `;
    
    iframe.srcdoc = docContent;
    container.appendChild(iframe);
    container.dataset.initialized = '1';
  });
}

// Escuchar mensajes del iframe (cambio de tamaño y persistencia de estado)
window.addEventListener('message', function(event) {
  if (!event.data) return;
  
  if (event.data.type === 'resize-iframe') {
    var iframe = document.querySelector('[data-widget-id="' + event.data.id + '"] iframe');
    if (iframe) {
      iframe.style.height = (event.data.height + 4) + 'px';
    }
  } else if (event.data.type === 'save-widget-state') {
    window.widgetStates = window.widgetStates || {};
    window.widgetStates[event.data.id] = event.data.state;
    fetch('/sessions/' + sessionId + '/widgets/' + encodeURIComponent(event.data.id) + '/state', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ state: event.data.state })
    });
  }
});

function renderAllMarkdown() {
  if (typeof marked === 'undefined') return;
  document.querySelectorAll('.md-content').forEach(function(el) {
    if (el.dataset.rendered) return;
    var raw = el.textContent;
    if (raw.trim()) {
      el.innerHTML = DOMPurify.sanitize(parseMarkdown(raw));
      initWidgets(el);
    }
    el.dataset.rendered = '1';
  });
}

document.addEventListener('DOMContentLoaded', renderAllMarkdown);

// Render markdown when session messages are loaded via fetch
new MutationObserver(function() { renderAllMarkdown(); }).observe(
  document.getElementById('main') || document.body,
  { childList: true, subtree: true }
);

// Auto-load session messages on page load if visiting an existing session
document.addEventListener('DOMContentLoaded', function() {
  if (window.location.pathname.startsWith('/sessions/')) {
    fetch('/sessions/' + sessionId + '/messages')
      .then(function(r) { return r.text(); })
      .then(function(h) {
        var main = document.getElementById('main');
        if (main) {
          main.innerHTML = h;
        }
      });
  }
});
