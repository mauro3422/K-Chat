var retryState = { count: 0, maxRetries: 3, streamTimeout: null };

function delay(ms) {
  return new Promise(function(resolve) { setTimeout(resolve, ms); });
}

function showRetryNotice(attempt, reason) {
  KairosUtils.showToast('Reintentando... (' + attempt + '/' + retryState.maxRetries + ') - ' + reason, 'warning');
  logUI('stream_retry', 'intento ' + attempt + '/' + retryState.maxRetries + ' - ' + reason);
}

export function scheduleRetry(form, input, asstDiv, lastUserMessageText, reason) {
  retryState.count++;
  showRetryNotice(retryState.count, reason);
  asstDiv.remove();
  input.value = lastUserMessageText;
  return delay(2000 * retryState.count).then(function doScheduledSubmit() {
    form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
  });
}

export function shouldRetry(hasContent, hasSuccessfulTools) {
  return retryState.count < retryState.maxRetries && !hasContent && !hasSuccessfulTools;
}

export function incrementRetry() {
  retryState.count++;
}

export function resetRetryCount() {
  retryState.count = 0;
}

export function getRetryCount() {
  return retryState.count;
}

export function getMaxRetries() {
  return retryState.maxRetries;
}

export function getStreamTimeout() {
  return retryState.streamTimeout || 120000;
}

export const RetryHandler = {
  delay,
  showRetryNotice,
  scheduleRetry,
  shouldRetry,
  incrementRetry,
  resetRetryCount,
  getRetryCount,
  getMaxRetries,
  getStreamTimeout
};
window.RetryHandler = RetryHandler;
