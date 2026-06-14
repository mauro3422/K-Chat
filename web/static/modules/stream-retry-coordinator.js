import { RetryHandler } from './retry-handler.js';
import { StreamErrorHandler } from './stream-error-handler.js';
import { Utils } from './utils.js';

export function attemptRetry(params) {
  var asstDiv = params.asstDiv;
  var form = params.form;
  var input = params.input;
  var lastUserMessageText = params.lastUserMessageText;
  var reason = params.reason;
  var hasContent = params.hasContent;
  var retryController = params.retryController || RetryHandler;

  if (!retryController.shouldRetry(hasContent)) {
    return false;
  }

  retryController.scheduleRetry(form, input, asstDiv, lastUserMessageText, reason);
  return true;
}

export function shouldAutoRetryEmptyResponse(params) {
  var hasContent = !!params.hasContent;
  var hadReasoning = !!params.hadReasoning;
  var hadToolCalls = !!params.hadToolCalls;
  var retryController = params.retryController || RetryHandler;
  if (hadReasoning || hadToolCalls) {
    return false;
  }
  return retryController.shouldRetry(hasContent);
}

export function handleRetryFinalization(params) {
  var asstDiv = params.asstDiv;
  var input = params.input;
  var hasContent = params.hasContent;
  var reason = params.reason;
  var retryController = params.retryController || RetryHandler;

  StreamErrorHandler.markCallingPillsError(asstDiv);

  if (!hasContent) {
    StreamErrorHandler.showRetryMessage(asstDiv, reason);
  }

  retryController.resetRetryCount();
  Utils.finalizeStream(input);
}
