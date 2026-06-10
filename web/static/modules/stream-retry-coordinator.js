export function attemptRetry(params) {
  var asstDiv = params.asstDiv;
  var form = params.form;
  var input = params.input;
  var lastUserMessageText = params.lastUserMessageText;
  var reason = params.reason;
  var hasContent = params.hasContent;
  var hasSuccessfulTools = params.hasSuccessfulTools;

  if (!RetryHandler.shouldRetry(hasContent, hasSuccessfulTools)) {
    return false;
  }

  RetryHandler.scheduleRetry(form, input, asstDiv, lastUserMessageText, reason);
  return true;
}

export function handleRetryFinalization(params) {
  var asstDiv = params.asstDiv;
  var input = params.input;
  var hasContent = params.hasContent;
  var reason = params.reason;

  StreamErrorHandler.markCallingPillsError(asstDiv);

  if (!hasContent) {
    StreamErrorHandler.showRetryMessage(asstDiv, reason);
  }

  RetryHandler.resetRetryCount();
  input.disabled = false;
  input.value = '';
  document.getElementById('spinner').textContent = '';
  input.focus();
  KairosUtils.scrollToBottom();
}
