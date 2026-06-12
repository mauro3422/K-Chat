import { RetryHandler } from './retry-handler.js';
import { StreamErrorHandler } from './stream-error-handler.js';
import { KairosUtils } from './utils.js';

export function attemptRetry(params) {
  var asstDiv = params.asstDiv;
  var form = params.form;
  var input = params.input;
  var lastUserMessageText = params.lastUserMessageText;
  var reason = params.reason;
  var hasContent = params.hasContent;

  if (!RetryHandler.shouldRetry(hasContent)) {
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
  KairosUtils.finalizeStream(input);
}
