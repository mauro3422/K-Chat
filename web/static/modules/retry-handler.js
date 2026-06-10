/* eslint-disable no-redeclare, no-unused-vars */
var RetryHandler = (function() {
  var retryCount = 0;
  var MAX_RETRIES = 2;
  var STREAM_TIMEOUT = 60000;

  function delay(ms) {
    return new Promise(function(resolve) { setTimeout(resolve, ms); });
  }

  function showRetryNotice(attempt, reason) {
    KairosUtils.showToast('Reintentando... (' + attempt + '/' + MAX_RETRIES + ') - ' + reason, 'warning');
    logUI('stream_retry', 'intento ' + attempt + '/' + MAX_RETRIES + ' - ' + reason);
  }

  function scheduleRetry(form, input, asstDiv, lastUserMessageText, reason) {
    retryCount++;
    showRetryNotice(retryCount, reason);
    asstDiv.remove();
    input.value = lastUserMessageText;
    return delay(2000 * retryCount).then(function doScheduledSubmit() {
      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    });
  }

  function shouldRetry(hasContent, hasSuccessfulTools) {
    return retryCount < MAX_RETRIES && !hasContent && !hasSuccessfulTools;
  }

  function incrementRetry() {
    retryCount++;
  }

  function resetRetryCount() {
    retryCount = 0;
  }

  function getRetryCount() {
    return retryCount;
  }

  function getMaxRetries() {
    return MAX_RETRIES;
  }

  function getStreamTimeout() {
    return STREAM_TIMEOUT;
  }

  return {
    delay: delay,
    showRetryNotice: showRetryNotice,
    scheduleRetry: scheduleRetry,
    shouldRetry: shouldRetry,
    incrementRetry: incrementRetry,
    resetRetryCount: resetRetryCount,
    getRetryCount: getRetryCount,
    getMaxRetries: getMaxRetries,
    getStreamTimeout: getStreamTimeout
  };
})();
