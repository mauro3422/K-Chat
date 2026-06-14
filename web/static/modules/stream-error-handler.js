import { Utils } from './utils.js';
import C from './dom-contracts.js';
import { DebugPanel } from './debug-panel.js';

function clearElement(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

export function markPillAsError(pill) {
  pill.className = C.TC_ITEM_ERROR;
  var toolName = pill.getAttribute('data-tool') || 'tool';
  pill.textContent = '✗ ' + toolName;
  DebugPanel.logUI('tool_error', toolName);
}

export function markCallingPillsError(asstDiv) {
  asstDiv.querySelectorAll('.' + C.TC_ITEM + '.calling').forEach(markPillAsError);
}

export function showRetryMessage(asstDiv, reason, errorType) {
  var bodyDiv = asstDiv.querySelector('.' + C.MSG_BODY);
  if (bodyDiv) {
    clearElement(bodyDiv);
    var card = document.createElement('div');
    card.className = C.ERROR_CARD;

    if (errorType === 'rate_limit') {
      card.className += ' rate-limit-card';
      var header = document.createElement('div');
      header.className = 'error-header rate-limit-header';
      header.textContent = '⏳ Modelo saturado';

      var detail = document.createElement('div');
      detail.className = 'error-detail';
      detail.textContent = reason;

      var hint = document.createElement('div');
      hint.className = 'error-hint';
      hint.textContent = 'Es un límite del proveedor, no de K-Chat. Podés intentar de nuevo en unos minutos.';

      card.appendChild(header);
      card.appendChild(detail);
      card.appendChild(hint);
    } else {
      var header = document.createElement('div');
      header.className = 'error-header';
      header.textContent = '⚠ Respuesta interrumpida';

      var detail = document.createElement('div');
      detail.className = 'error-detail';
      detail.textContent = reason;

      var button = document.createElement('button');
      button.type = 'button';
      button.className = 'error-retry-btn';
      button.textContent = 'Reintentar envío';

      card.appendChild(header);
      card.appendChild(detail);
      card.appendChild(button);
    }
    bodyDiv.appendChild(card);
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
