import { StreamErrorHandler } from './stream-error-handler.js';
import { RetryHandler } from './retry-handler.js';
import C from './dom-contracts.js';
import { StreamContext } from './stream-context.js';
import { executeStreamFetch } from './stream-fetcher.js';
import { attemptRetry } from './stream-retry-coordinator.js';

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

    logUI('stream_start', 'mensaje=' + text.substring(0, 40) + '...');

    var errorHandler = StreamErrorHandler.createStreamErrorHandler();
    KairosStream.on('error', errorHandler.handler);

    var timeoutId = null;

    var resetTimeout = function resetStreamTimeout() {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(function() {
        logUI('stream_timeout', RetryHandler.getStreamTimeout() / 1000 + 's sin respuesta, abortando');
        controller.abort();
      }, RetryHandler.getStreamTimeout());
    };

    timeoutId = setTimeout(function() {
      logUI('stream_timeout', RetryHandler.getStreamTimeout() / 1000 + 's sin respuesta, abortando');
      controller.abort();
    }, RetryHandler.getStreamTimeout());

    var context = new StreamContext(asstDiv);

    var fetchResult;
    try {
      fetchResult = await executeStreamFetch({
        sessionId: sessionId,
        defaultModel: defaultModel,
        text: text,
        controller: controller,
        errorHandler: errorHandler,
        context: context,
        onChunk: resetTimeout
      });
    } catch(e2) {
      clearTimeout(timeoutId);

      if (e2.name === 'AbortError') {
        logUI('stream_aborted', 'cancelado por nuevo mensaje');
        var bodyDiv = asstDiv.querySelector('.' + C.MSG_BODY);
        var isEmpty = !bodyDiv || bodyDiv.textContent === 'Pensando...' || bodyDiv.textContent === '';
        if (isEmpty) {
          asstDiv.remove();
        }
        KairosUtils.finalizeStream(input);
        return;
      }

      logUI('stream_error', e2.message);

      var hasSuccessfulTools = asstDiv.querySelectorAll('.' + C.TC_ITEM + '.ok').length > 0;
      if (attemptRetry({
        asstDiv: asstDiv,
        form: form,
        input: input,
        lastUserMessageText: lastUserMessageText,
        reason: 'error: ' + e2.message,
        hasContent: false,
        hasSuccessfulTools: hasSuccessfulTools
      })) {
        return;
      }

      StreamErrorHandler.markCallingPillsError(asstDiv);
      StreamErrorHandler.showRetryMessage(asstDiv, 'No se pudo recibir la respuesta después de ' + RetryHandler.getMaxRetries() + ' reintentos. Detalle: ' + KairosUtils.escHtml(e2.toString()));
      logUI('stream_error_final', 'falló definitivamente: ' + e2.message);
    }

    clearTimeout(timeoutId);

    var hasContent = fetchResult ? fetchResult.hasContent : false;

    var streamError = errorHandler.getError();
    if (streamError) {
      logUI('stream_backend_error', streamError.type + ': ' + streamError.message);

      var errorType = streamError.type || 'unknown';
      var errorMsg = streamError.message || 'Error desconocido';

      if (errorType === 'auth' || errorType === 'rate_limit') {
        StreamErrorHandler.showRetryMessage(asstDiv, errorMsg);
        RetryHandler.resetRetryCount();
        KairosUtils.finalizeStream(input);
        return;
      }

      hasSuccessfulTools = asstDiv.querySelectorAll('.' + C.TC_ITEM + '.ok').length > 0;
      if (attemptRetry({
        asstDiv: asstDiv,
        form: form,
        input: input,
        lastUserMessageText: lastUserMessageText,
        reason: errorMsg,
        hasContent: hasContent,
        hasSuccessfulTools: hasSuccessfulTools
      })) {
        return;
      }

      StreamErrorHandler.showRetryMessage(asstDiv, errorMsg + ' (después de ' + RetryHandler.getMaxRetries() + ' reintentos)');
      RetryHandler.resetRetryCount();
      KairosUtils.finalizeStream(input);
      return;
    }

    if (context.getReasoningEls().length) {
      context.getReasoningEls()[context.getReasoningEls().length - 1].querySelector('summary').textContent = 'Razonamiento';
      logUI('reasoning_done', context.getReasoningEls().length + ' fases');
    }

    hasSuccessfulTools = asstDiv.querySelectorAll('.tc-item.ok').length > 0;
    if (!hasContent) {
      if (attemptRetry({
        asstDiv: asstDiv,
        form: form,
        input: input,
        lastUserMessageText: lastUserMessageText,
        reason: 'respuesta vacía',
        hasContent: false,
        hasSuccessfulTools: hasSuccessfulTools
      })) {
        return;
      }

      StreamErrorHandler.markCallingPillsError(asstDiv);
      StreamErrorHandler.showRetryMessage(asstDiv, 'La respuesta estuvo vacía después de ' + RetryHandler.getMaxRetries() + ' reintentos. Puede ser un problema temporal del modelo.');
      logUI('stream_empty_final', 'sin contenido después de ' + RetryHandler.getMaxRetries() + ' reintentos');
    } else {
      RetryHandler.resetRetryCount();
      refreshSidebar();
      if (typeof debugVisible !== 'undefined' && debugVisible) refreshDebug();
    }

    KairosUtils.finalizeStream(input);
  }

};
window.StreamOrchestrator = StreamOrchestrator;
