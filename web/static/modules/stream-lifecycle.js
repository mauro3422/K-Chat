import { StreamErrorHandler } from './stream-error-handler.js';
import { attemptRetry, shouldAutoRetryEmptyResponse } from './stream-retry-coordinator.js';
import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';
import { SessionContext } from './session-context.js';
import { logUI } from './log-ui.js';
import { ApiClient } from './api-client.js';

export function refreshSidebar() {
  ApiClient.sidebar().then(function(h){
    var el = document.getElementById('session-list');
    if (el) el.innerHTML = h;
  }).catch(function(err) { console.error('Sidebar refresh failed:', err); });
}

function isEmptyAssistant(asstDiv) {
  var bodyDiv = asstDiv.querySelector('.' + C.MSG_BODY);
  return !bodyDiv || bodyDiv.textContent === 'Pensando...' || bodyDiv.textContent === '';
}

export function handleAbortError(params, retryController) {
  var asstDiv = params.asstDiv;
  var input = params.input;
  logUI('stream_aborted', 'cancelado por nuevo mensaje');
  if (isEmptyAssistant(asstDiv)) {
    asstDiv.remove();
  }
  retryController.resetRetryCount();
  KairosUtils.finalizeStream(input);
}

export function handleTransportError(params, retryController, error) {
  var asstDiv = params.asstDiv;
  var form = params.form;
  var input = params.input;
  var lastUserMessageText = params.lastUserMessageText;

  logUI('stream_error', error.message);

  var hasSuccessfulTools = asstDiv.querySelectorAll('.' + C.TC_ITEM + '.ok').length > 0;
  if (attemptRetry({
    asstDiv: asstDiv,
    form: form,
    input: input,
    lastUserMessageText: lastUserMessageText,
    reason: 'error: ' + error.message,
    hasContent: false,
    hasSuccessfulTools: hasSuccessfulTools,
    retryController: retryController
  })) {
    return true;
  }

  StreamErrorHandler.markCallingPillsError(asstDiv);
  StreamErrorHandler.showRetryMessage(asstDiv, 'No se pudo recibir la respuesta después de ' + retryController.getMaxRetries() + ' reintentos. Detalle: ' + KairosUtils.escHtml(error.toString()));
  logUI('stream_error_final', 'falló definitivamente: ' + error.message);
  retryController.resetRetryCount();
  return false;
}

export function handleBackendError(params, retryController, streamError, hasContent) {
  var asstDiv = params.asstDiv;
  var form = params.form;
  var input = params.input;
  var lastUserMessageText = params.lastUserMessageText;

  logUI('stream_backend_error', streamError.type + ': ' + streamError.message);

  var errorType = streamError.type || 'unknown';
  var errorMsg = streamError.message || 'Error desconocido';

  if (errorType === 'auth' || errorType === 'rate_limit') {
    StreamErrorHandler.showRetryMessage(asstDiv, errorMsg);
    retryController.resetRetryCount();
    KairosUtils.finalizeStream(input);
    return true;
  }

  var hasSuccessfulTools = asstDiv.querySelectorAll('.' + C.TC_ITEM + '.ok').length > 0;
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
    return true;
  }

  StreamErrorHandler.showRetryMessage(asstDiv, errorMsg + ' (después de ' + retryController.getMaxRetries() + ' reintentos)');
  retryController.resetRetryCount();
  KairosUtils.finalizeStream(input);
  return false;
}

export function handleEmptyResponse(params, retryController, context, hasContent) {
  var asstDiv = params.asstDiv;
  var form = params.form;
  var input = params.input;
  var lastUserMessageText = params.lastUserMessageText;

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
    return false;
  }

  if (attemptRetry({
    asstDiv: asstDiv,
    form: form,
    input: input,
    lastUserMessageText: lastUserMessageText,
    reason: 'respuesta vacía',
    hasContent: false,
    hasSuccessfulTools: asstDiv.querySelectorAll('.' + C.TC_ITEM + '.ok').length > 0,
    retryController: retryController
  })) {
    return true;
  }

  if (retryController.getRetryCount() >= retryController.getMaxRetries()) {
    StreamErrorHandler.markCallingPillsError(asstDiv);
    StreamErrorHandler.showRetryMessage(asstDiv, 'La respuesta estuvo vacía después de ' + retryController.getMaxRetries() + ' reintentos. Puede ser un problema temporal del modelo.');
    logUI('stream_empty_final', 'sin contenido después de ' + retryController.getMaxRetries() + ' reintentos');
    retryController.resetRetryCount();
  }
  return false;
}
