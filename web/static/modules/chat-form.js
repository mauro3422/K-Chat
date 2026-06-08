var KairosForm = (function() {
  var lastUserMessageText = '';
  var currentController = null;
  var retryCount = 0;
  var MAX_RETRIES = 2;

  function retryLastMessage() {
    var lastAsstMsg = document.querySelector('.msg.assistant:last-child');
    if (lastAsstMsg && lastAsstMsg.querySelector('.error-card')) {
      lastAsstMsg.remove();
    }
    var input = document.getElementById('msg-input');
    if (input) {
      input.value = lastUserMessageText;
      var form = document.getElementById('chat-form');
      if (form) {
        form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      }
    }
  }

  function showRetryNotice(attempt, reason) {
    KairosUtils.showToast('Reintentando... (' + attempt + '/' + MAX_RETRIES + ') - ' + reason, 'warning');
    logUI('stream_retry', 'intento ' + attempt + '/' + MAX_RETRIES + ' - ' + reason);
  }

  function delay(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }

  function showRetryMessage(asstDiv, reason) {
    var bodyDiv = asstDiv.querySelector('.msg-body');
    if (bodyDiv) {
      bodyDiv.innerHTML =
        '<div class="error-card">' +
          '<div class="error-header">&#9888; Respuesta interrumpida</div>' +
          '<div class="error-detail">' + reason + '</div>' +
          '<button class="error-retry-btn" onclick="KairosForm.retry()">Reintentar envío</button>' +
        '</div>';
    }
  }

  function init() {
    document.addEventListener('submit', function(e) {
      var form = e.target;
      if (form.id !== 'chat-form') return;
      e.preventDefault();

      var input = document.getElementById('msg-input');
      if (!input) input = form.querySelector('input[name="message"]');
      if (!input) return;
      var text = input.value.trim();
      if (!text) return;

      if (currentController) currentController.abort();
      currentController = new AbortController();

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
      KairosUtils.esc();

      (async function() {
          var buf = '';
          var hasContent = false;
          var tokenCount = 0;
          var state = {
            asstDiv: asstDiv,
            bodyDivs: [asstDiv.querySelector('.msg-body')],
            reasoningEls: [],
            contentTexts: [''],
            reasoningText: '',
            firstToken: true
          };

          logUI('stream_start', 'mensaje=' + text.substring(0, 40) + '...');

          var timeoutId = setTimeout(function() {
            logUI('stream_timeout', '60s sin respuesta, abortando');
            currentController.abort();
          }, 60000);

          var streamError = null;
          
          // Capturar eventos de error del stream
          var originalEmit = KairosStream.emit;
          KairosStream.emit = function(event, data, state) {
            if (event === 'error') {
              streamError = data;
            }
            return originalEmit.apply(this, arguments);
          };
          
          try {
            var resp = await fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(defaultModel), {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded'},
              body: 'message=' + encodeURIComponent(text),
              signal: currentController.signal
            });
            
            if (resp.status === 401) {
              streamError = { type: 'auth', message: 'Error de autenticación. Verifica tu API key.' };
            } else if (resp.status === 429) {
              streamError = { type: 'rate_limit', message: 'Límite de tasa alcanzado. Espera un momento.' };
            } else if (resp.status >= 500) {
              streamError = { type: 'server', message: 'Error del servidor (' + resp.status + ')' };
            }
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
                if (state.firstToken) {
                  state.bodyDivs[0].textContent = '';
                  state.firstToken = false;
                  logUI('pensando_cleared', '' + msg.t);
                }
                if (msg.t === 'content' && msg.d && msg.d.trim()) {
                  hasContent = true;
                  tokenCount++;
                }
                KairosStream.emit(msg.t, msg.d, state);
              }
            }

            logUI('stream_complete', 'tokens=' + tokenCount + ' hasContent=' + hasContent);
            clearTimeout(timeoutId);

            if (!hasContent && retryCount < MAX_RETRIES) {
              retryCount++;
              showRetryNotice(retryCount, 'respuesta vacía');
              asstDiv.remove();
              input.value = lastUserMessageText;
              await delay(2000 * retryCount);
              form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
              return;
            }

            var callingPills = asstDiv.querySelectorAll('.tc-item.calling');
            callingPills.forEach(function(pill) {
              pill.className = 'tc-item error';
              var toolName = pill.getAttribute('data-tool') || 'tool';
              pill.innerHTML = '&#10007; ' + KairosUtils.escHtml(toolName);
              logUI('tool_error', toolName);
            });

            if (state.reasoningEls.length) {
              state.reasoningEls[state.reasoningEls.length - 1].querySelector('summary').textContent = 'Razonamiento';
              logUI('reasoning_done', state.reasoningEls.length + ' fases');
            }

            for (var idx = 0; idx < state.contentTexts.length; idx++) {
              if (state.contentTexts[idx]) {
                state.bodyDivs[idx].innerHTML = DOMPurify.sanitize(KairosMarkdown.parse(state.contentTexts[idx]));
                KairosWidgets.initAll(state.bodyDivs[idx]);
              }
            }

            if (!hasContent) {
              showRetryMessage(asstDiv, 'La respuesta estuvo vacía después de ' + MAX_RETRIES + ' reintentos. Puede ser un problema temporal del modelo.');
              logUI('stream_empty_final', 'sin contenido después de ' + MAX_RETRIES + ' reintentos');
            } else {
              retryCount = 0;
              refreshSidebar();
              if (typeof debugVisible !== 'undefined' && debugVisible) refreshDebug();
            }
          } catch(e2) {
            clearTimeout(timeoutId);
            KairosStream.emit = originalEmit;
            
            if (e2.name === 'AbortError') {
              logUI('stream_aborted', 'cancelado por nuevo mensaje');
              asstDiv.remove();
              input.disabled = false;
              input.value = '';
              document.getElementById('spinner').textContent = '';
              input.focus();
              return;
            }

            logUI('stream_error', e2.message);

            if (retryCount < MAX_RETRIES) {
              retryCount++;
              showRetryNotice(retryCount, 'error: ' + e2.message);
              asstDiv.remove();
              input.value = lastUserMessageText;
              await delay(2000 * retryCount);
              form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
              return;
            }

            var callingPills = asstDiv.querySelectorAll('.tc-item.calling');
            callingPills.forEach(function(pill) {
              pill.className = 'tc-item error';
              var toolName = pill.getAttribute('data-tool') || 'tool';
              pill.innerHTML = '&#10007; ' + KairosUtils.escHtml(toolName);
              logUI('tool_error', toolName);
            });

            showRetryMessage(asstDiv, 'No se pudo recibir la respuesta después de ' + MAX_RETRIES + ' reintentos. Detalle: ' + KairosUtils.escHtml(e2.toString()));
            logUI('stream_error_final', 'falló definitivamente: ' + e2.message);
          }
          
          KairosStream.emit = originalEmit;
          
          // Manejar errores del backend
          if (streamError) {
            logUI('stream_backend_error', streamError.type + ': ' + streamError.message);
            
            var errorType = streamError.type || 'unknown';
            var errorMsg = streamError.message || 'Error desconocido';
            
            // No reintentar errores permanentes
            if (errorType === 'auth' || errorType === 'rate_limit') {
              showRetryMessage(asstDiv, errorMsg);
              retryCount = 0;
              input.disabled = false;
              input.value = '';
              document.getElementById('spinner').textContent = '';
              input.focus();
              KairosUtils.esc();
              return;
            }
            
            // Reintentar errores temporales
            if (retryCount < MAX_RETRIES) {
              retryCount++;
              showRetryNotice(retryCount, errorMsg);
              asstDiv.remove();
              input.value = lastUserMessageText;
              await delay(2000 * retryCount);
              form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
              return;
            }
            
            showRetryMessage(asstDiv, errorMsg + ' (después de ' + MAX_RETRIES + ' reintentos)');
            retryCount = 0;
          }
        input.disabled = false;
        input.value = '';
        document.getElementById('spinner').textContent = '';
        input.focus();
        KairosUtils.esc();
      })();
    });
  }

  return {
    init: init,
    retry: retryLastMessage
  };
})();
