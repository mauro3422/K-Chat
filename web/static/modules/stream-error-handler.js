import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';
import { KairosDebug } from '../debug.js';

export function markPillAsError(pill) {
  pill.className = C.TC_ITEM_ERROR;
  var toolName = pill.getAttribute('data-tool') || 'tool';
  pill.innerHTML = '&#10007; ' + KairosUtils.escHtml(toolName);
  KairosDebug.logUI('tool_error', toolName);
}

export function markCallingPillsError(asstDiv) {
  asstDiv.querySelectorAll('.' + C.TC_ITEM + '.calling').forEach(markPillAsError);
}

export function showRetryMessage(asstDiv, reason) {
  var bodyDiv = asstDiv.querySelector('.' + C.MSG_BODY);
  if (bodyDiv) {
      bodyDiv.innerHTML =
      '<div class="' + C.ERROR_CARD + '">' +
        '<div class="error-header">&#9888; Respuesta interrumpida</div>' +
        '<div class="error-detail">' + KairosUtils.escHtml(reason) + '</div>' +
        '<button type="button" class="error-retry-btn">Reintentar envío</button>' +
      '</div>';
  }
}

export function createStreamErrorHandler() {
  var streamError = null;
  var handler = function captureStreamError(event, data) {
    if (event === 'error') {
      streamError = data;
    }
  };
  return {
    handler: handler,
    getError: function() { return streamError; },
    clearError: function() { streamError = null; }
  };
}

export const StreamErrorHandler = {
  markPillAsError,
  markCallingPillsError,
  showRetryMessage,
  createStreamErrorHandler
};
