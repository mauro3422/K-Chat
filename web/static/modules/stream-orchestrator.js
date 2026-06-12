import { StreamErrorHandler } from './stream-error-handler.js';
import { createRetryController } from './retry-handler.js';
import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';
import { KairosStream } from './stream-dispatcher.js';
import { StreamContext } from './stream-context.js';
import { executeStreamFetch } from './stream-fetcher.js';
import { attemptRetry, shouldAutoRetryEmptyResponse } from './stream-retry-coordinator.js';
import { KairosDebug, refreshDebug } from '../debug.js';
import { SessionContext } from './session-context.js';

function refreshSidebar() {
  var urlBuilder = SessionContext.createSessionUrlBuilder();
  fetch(urlBuilder.sidebar()).then(function(r){ return r.text(); }).then(function(h){
    var el = document.getElementById('session-list');
    if (el) el.innerHTML = h;
  }).catch(function(err) { console.error('Sidebar refresh failed:', err); });
}

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
    var retryController = params.retryController || createRetryController();

    logUI('stream_start', 'mensaje=' + text.substring(0, 40) + '...');

    var errorHandler = StreamErrorHandler.createStreamErrorHandler();
    KairosStream.on('error', errorHandler.handler);

    var timeoutId = null;
    var streamTimeout = retryController.getStreamTimeout();

    var resetTimeout = function resetStreamTimeout() {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(function() {
        logUI('stream_timeout', streamTimeout / 1000 + 's sin respuesta, abortando');
        controller.abort();
      }, streamTimeout);
    };

    timeoutId = setTimeout(function() {
      logUI('stream_timeout', streamTimeout / 1000 + 's sin respuesta, abortando');
      controller.abort();
    }, streamTimeout);

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
        retryController.resetRetryCount();
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
        hasSuccessfulTools: hasSuccessfulTools,
        retryController: retryController
      })) {
        return;
      }

      StreamErrorHandler.markCallingPillsError(asstDiv);
      StreamErrorHandler.showRetryMessage(asstDiv, 'No se pudo recibir la respuesta después de ' + retryController.getMaxRetries() + ' reintentos. Detalle: ' + KairosUtils.escHtml(e2.toString()));
      logUI('stream_error_final', 'falló definitivamente: ' + e2.message);
      retryController.resetRetryCount();
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
        retryController.resetRetryCount();
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
        hasSuccessfulTools: hasSuccessfulTools,
        retryController: retryController
      })) {
        return;
      }

      StreamErrorHandler.showRetryMessage(asstDiv, errorMsg + ' (después de ' + retryController.getMaxRetries() + ' reintentos)');
      retryController.resetRetryCount();
      KairosUtils.finalizeStream(input);
      return;
    }

    if (context.getReasoningEls().length) {
      context.getReasoningEls()[context.getReasoningEls().length - 1].querySelector('summary').textContent = 'Razonamiento';
      logUI('reasoning_done', context.getReasoningEls().length + ' fases');
    }

    hasSuccessfulTools = asstDiv.querySelectorAll('.tc-item.ok').length > 0;
    if (!hasContent) {
      var hadReasoning = context.getReasoningEls().length > 0;
      var hadToolCalls = asstDiv.querySelectorAll('.' + C.TC_ITEM).length > 0;

      if (!shouldAutoRetryEmptyResponse({
        hasContent: hasContent,
        hadReasoning: hadReasoning,
        hadToolCalls: hadToolCalls,
        retryController: retryController
      })) {
        StreamErrorHandler.markCallingPillsError(asstDiv);
        StreamErrorHandler.showRetryMessage(
          asstDiv,
          'La respuesta quedó vacía después de razonamiento o herramientas. No se reintentó automáticamente.'
        );
        logUI('stream_empty_no_retry', 'sin contenido con razonamiento/herramientas');
        retryController.resetRetryCount();
      } else if (attemptRetry({
        asstDiv: asstDiv,
        form: form,
        input: input,
        lastUserMessageText: lastUserMessageText,
        reason: 'respuesta vacía',
        hasContent: false,
        hasSuccessfulTools: hasSuccessfulTools,
        retryController: retryController
      })) {
        return;
      }

      if (retryController.getRetryCount() >= retryController.getMaxRetries()) {
        StreamErrorHandler.markCallingPillsError(asstDiv);
        StreamErrorHandler.showRetryMessage(asstDiv, 'La respuesta estuvo vacía después de ' + retryController.getMaxRetries() + ' reintentos. Puede ser un problema temporal del modelo.');
        logUI('stream_empty_final', 'sin contenido después de ' + retryController.getMaxRetries() + ' reintentos');
        retryController.resetRetryCount();
      }
    } else {
      retryController.resetRetryCount();
      refreshSidebar();
      if (KairosDebug.debugVisible) refreshDebug();
    }

    KairosUtils.finalizeStream(input);
  }

};
