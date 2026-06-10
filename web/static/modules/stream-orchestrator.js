export const StreamOrchestrator = {

  async startStream(params) {
    var text = params.text;
    var form = params.form;
    var input = params.input;
    var asstDiv = params.asstDiv;
    var lastUserMessageText = params.lastUserMessageText;
    var controller = params.controller;
    var sessionId = params.sessionId;
    var defaultModel = params.defaultModel;

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
        controller.abort();
      }, RetryHandler.getStreamTimeout());
    };
    var timeoutId = setTimeout(function() {
      logUI('stream_timeout', RetryHandler.getStreamTimeout() / 1000 + 's sin respuesta, abortando');
      controller.abort();
    }, RetryHandler.getStreamTimeout());

    try {
      var resp = await fetch('/chat/' + sessionId + '?model=' + encodeURIComponent(defaultModel), {
        method: 'POST',
        headers: {'Content-Type': 'application/x-www-form-urlencoded'},
        body: 'message=' + encodeURIComponent(text),
        signal: controller.signal
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
  }

};
