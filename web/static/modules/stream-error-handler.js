/* eslint-disable no-redeclare, no-unused-vars */
var StreamErrorHandler = (function() {

  function markPillAsError(pill) {
    pill.className = 'tc-item error';
    var toolName = pill.getAttribute('data-tool') || 'tool';
    pill.innerHTML = '&#10007; ' + KairosUtils.escHtml(toolName);
    logUI('tool_error', toolName);
  }

  function markCallingPillsError(asstDiv) {
    asstDiv.querySelectorAll('.tc-item.calling').forEach(markPillAsError);
  }

  function showRetryMessage(asstDiv, reason) {
    var bodyDiv = asstDiv.querySelector('.msg-body');
    if (bodyDiv) {
      bodyDiv.innerHTML =
        '<div class="error-card">' +
          '<div class="error-header">&#9888; Respuesta interrumpida</div>' +
          '<div class="error-detail">' + KairosUtils.escHtml(reason) + '</div>' +
          '<button class="error-retry-btn" onclick="KairosForm.retry()">Reintentar envío</button>' +
        '</div>';
    }
  }

  function createStreamErrorHandler() {
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

  return {
    markPillAsError: markPillAsError,
    markCallingPillsError: markCallingPillsError,
    showRetryMessage: showRetryMessage,
    createStreamErrorHandler: createStreamErrorHandler
  };
})();
