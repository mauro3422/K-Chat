/* eslint-disable no-redeclare, no-unused-vars */
var KairosForm = (function() {
  var lastUserMessageText = '';
  var currentController = null;

  function retryLastMessage() {
    var lastAsstMsg = document.querySelector('.msg.assistant:last-child');
    if (lastAsstMsg && lastAsstMsg.querySelector('.error-card')) {
      lastAsstMsg.remove();
    }

    var lastUserText = '';
    var userMsgs = document.querySelectorAll('.msg.user');
    if (userMsgs.length > 0) {
      var lastUserBody = userMsgs[userMsgs.length - 1].querySelector('.msg-body');
      if (lastUserBody) {
        lastUserText = lastUserBody.innerText || lastUserBody.textContent || '';
      }
    }

    var input = document.getElementById('msg-input');
    if (input) {
      input.disabled = false;
      input.value = lastUserText.trim() || lastUserMessageText;
      var form = document.getElementById('chat-form');
      if (form) {
        form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      }
    }
  }

  function init() {
    document.addEventListener('submit', function onSubmit(e) {
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
        '<div class="msg user"><div class="msg-label">Tu</div><div class="msg-body">' + KairosUtils.escHtml(text) + '</div></div>');
      var asstDiv = document.createElement('div');
      asstDiv.className = 'msg assistant';
      asstDiv.innerHTML = '<div class="msg-label">Kairos</div><div class="msg-body md-content">Pensando...</div>';
      document.getElementById('messages').appendChild(asstDiv);
      KairosUtils.scrollToBottom();

      (async function handleStream() {
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

          var errorHandler = StreamErrorHandler.createStreamErrorHandler();
          KairosStream.on('error', errorHandler.handler);

          var resetTimeout = function resetStreamTimeout() {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(function() {
              logUI('stream_timeout', RetryHandler.getStreamTimeout() / 1000 + 's sin respuesta, abortando');
              currentController.abort();
            }, RetryHandler.getStreamTimeout());
          };
          var timeoutId = setTimeout(function() {
            logUI('stream_timeout', RetryHandler.getStreamTimeout() / 1000 + 's sin respuesta, abortando');
            currentController.abort();
          }, RetryHandler.getStreamTimeout());

          try {
            var resp = await fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(defaultModel), {
              method: 'POST',
              headers: {'Content-Type': 'application/x-www-form-urlencoded'},
              body: 'message=' + encodeURIComponent(text),
              signal: currentController.signal
            });

            if (resp.status === 401) {
              errorHandler.handler('error', { type: 'auth', message: 'Error de autenticación. Verifica tu API key.' });
            } else if (resp.status === 429) {
              errorHandler.handler('error', { type: 'rate_limit', message: 'Límite de tasa alcanzado. Espera un momento.' });
            } else if (resp.status >= 500) {
              errorHandler.handler('error', { type: 'server', message: 'Error del servidor (' + resp.status + ')' });
            }
            var reader = resp.body.getReader();
            var decoder = new TextDecoder();

            while (true) {
              var r = await reader.read();
              if (r.done) break;
              resetTimeout();
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

            var hasSuccessfulTools = asstDiv.querySelectorAll('.tc-item.ok').length > 0;
            if (!hasContent && RetryHandler.shouldRetry(false, hasSuccessfulTools)) {
              await RetryHandler.scheduleRetry(form, input, asstDiv, lastUserMessageText, 'respuesta vacía');
              return;
            }

            StreamErrorHandler.markCallingPillsError(asstDiv);

            if (state.reasoningEls.length) {
              state.reasoningEls[state.reasoningEls.length - 1].querySelector('summary').textContent = 'Razonamiento';
              logUI('reasoning_done', state.reasoningEls.length + ' fases');
            }

            if (!hasContent) {
              StreamErrorHandler.showRetryMessage(asstDiv, 'La respuesta estuvo vacía después de ' + RetryHandler.getMaxRetries() + ' reintentos. Puede ser un problema temporal del modelo.');
              logUI('stream_empty_final', 'sin contenido después de ' + RetryHandler.getMaxRetries() + ' reintentos');
            } else {
              RetryHandler.resetRetryCount();
              refreshSidebar();
              if (typeof debugVisible !== 'undefined' && debugVisible) refreshDebug();
            }
          } catch(e2) {
            clearTimeout(timeoutId);

            if (e2.name === 'AbortError') {
              logUI('stream_aborted', 'cancelado por nuevo mensaje');
              var bodyDiv = asstDiv.querySelector('.msg-body');
              var isEmpty = !bodyDiv || bodyDiv.textContent === 'Pensando...' || bodyDiv.textContent === '';
              if (isEmpty) {
                asstDiv.remove();
              }
              input.disabled = false;
              input.value = '';
              document.getElementById('spinner').textContent = '';
              input.focus();
              return;
            }

            logUI('stream_error', e2.message);

            var hasSuccessfulTools = asstDiv.querySelectorAll('.tc-item.ok').length > 0;
            if (RetryHandler.shouldRetry(false, hasSuccessfulTools)) {
              await RetryHandler.scheduleRetry(form, input, asstDiv, lastUserMessageText, 'error: ' + e2.message);
              return;
            }

            StreamErrorHandler.markCallingPillsError(asstDiv);

            StreamErrorHandler.showRetryMessage(asstDiv, 'No se pudo recibir la respuesta después de ' + RetryHandler.getMaxRetries() + ' reintentos. Detalle: ' + KairosUtils.escHtml(e2.toString()));
            logUI('stream_error_final', 'falló definitivamente: ' + e2.message);
          }

          var streamError = errorHandler.getError();
          if (streamError) {
            logUI('stream_backend_error', streamError.type + ': ' + streamError.message);

            var errorType = streamError.type || 'unknown';
            var errorMsg = streamError.message || 'Error desconocido';

            if (errorType === 'auth' || errorType === 'rate_limit') {
              StreamErrorHandler.showRetryMessage(asstDiv, errorMsg);
              RetryHandler.resetRetryCount();
              input.disabled = false;
              input.value = '';
              document.getElementById('spinner').textContent = '';
              input.focus();
              KairosUtils.scrollToBottom();
              return;
            }

            var hasSuccessfulTools = asstDiv.querySelectorAll('.tc-item.ok').length > 0;
            if (RetryHandler.shouldRetry(false, hasSuccessfulTools)) {
              await RetryHandler.scheduleRetry(form, input, asstDiv, lastUserMessageText, errorMsg);
              return;
            }

            StreamErrorHandler.showRetryMessage(asstDiv, errorMsg + ' (después de ' + RetryHandler.getMaxRetries() + ' reintentos)');
            RetryHandler.resetRetryCount();
          }
        input.disabled = false;
        input.value = '';
        document.getElementById('spinner').textContent = '';
        input.focus();
        KairosUtils.scrollToBottom();
      })();
    });
  }

  function resetForm() {
    lastUserMessageText = '';
    RetryHandler.resetRetryCount();
  }

  return {
    init: init,
    retry: retryLastMessage,
    reset: resetForm
  };
})();
