import { KairosUtils } from './utils.js';
import C from './dom-contracts.js';
import { KairosDebugPanel } from './debug-panel.js';

function clearElement(el) {
  while (el.firstChild) {
    el.removeChild(el.firstChild);
  }
}

export function markPillAsError(pill) {
  pill.className = C.TC_ITEM_ERROR;
  var toolName = pill.getAttribute('data-tool') || 'tool';
  pill.textContent = '✗ ' + toolName;
  KairosDebugPanel.logUI('tool_error', toolName);
}

export function markCallingPillsError(asstDiv) {
  asstDiv.querySelectorAll('.' + C.TC_ITEM + '.calling').forEach(markPillAsError);
}

export function showRetryMessage(asstDiv, reason) {
  var bodyDiv = asstDiv.querySelector('.' + C.MSG_BODY);
  if (bodyDiv) {
    clearElement(bodyDiv);
    var card = document.createElement('div');
    card.className = C.ERROR_CARD;

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
